from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from assessor_sync.management.commands.import_assessor import (
    COUNTY_ZIP_URL,
    DATASETS,
    _import_code_descriptions,
    _import_dataset,
    _load_mappings,
    _seed_code_mappings,
    _seed_primary_use_codes,
)


@dataclass(frozen=True)
class TableSync:
    table: str
    member_name: str
    key_columns: tuple[str, ...]
    report_label: str


TABLES = (
    TableSync("assessor_rollup", DATASETS["assessor_rollup"], ("parcel_number",), "parcels"),
    TableSync("sales", DATASETS["sales"], ("saleid", "parcel_number", "recording_number", "excise_number"), "sales"),
    TableSync("land", DATASETS["land"], ("parcelnumber", "prop_val_yr", "land_seg_id"), "land"),
    TableSync(
        "improvements",
        DATASETS["improvements"],
        ("parcelnumber", "imprv_id", "segment_id", "imprv_det_type_cd", "imprv_det_class_cd"),
        "improvements",
    ),
)
REPORT_ROW_LIMIT = 200
AUDIT_EXCLUDED_COLUMNS = {
    # The assessor export appears to churn AID values across most parcels, which
    # creates huge audit rows without useful Parcel Book signal.
    "assessor_rollup": {"aid"},
}
COMPACT_AUDIT_COLUMNS = {
    "assessor_rollup": (
        "parcel_number",
        "owner_name",
        "situs_street_number",
        "situs_street_name",
        "situs_city_state_zip",
        "land_use_code",
        "land_use_description",
        "assessed_value",
        "total_market_value",
        "acres",
    ),
    "sales": (
        "saleid",
        "parcel_number",
        "recording_number",
        "excise_number",
        "sale_date",
        "sale_date_iso",
        "sale_price",
        "sale_price_num",
        "seller_name",
        "buyer_name",
        "deed_type",
    ),
    "land": ("parcelnumber", "prop_val_yr", "land_seg_id", "size_acres", "size_acres_num", "market_value", "market_value_num"),
    "improvements": (
        "parcelnumber",
        "imprv_id",
        "segment_id",
        "imprv_det_type_cd",
        "imprv_det_type_description",
        "imprv_val",
        "imprv_val_num",
    ),
}


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def key_expr(alias: str, columns: Iterable[str]) -> str:
    parts = ", ".join(f"NULLIF({alias}.{quote_ident(col)}::text, '')" for col in columns)
    return f"concat_ws('|', {parts})"


def row_json_expr(alias: str, excluded_columns: Iterable[str] = ()) -> str:
    expr = f"(to_jsonb({alias}) - 'id'"
    for column in excluded_columns:
        expr += f" - '{column}'"
    return expr + ")"


def compact_row_json_expr(alias: str, table_name: str, available_columns: Iterable[str]) -> str:
    available = set(available_columns)
    pairs = []
    for column in COMPACT_AUDIT_COLUMNS.get(table_name, ()):
        if column in available:
            pairs.append(f"'{column}', {alias}.{quote_ident(column)}")
    if not pairs:
        return "'{}'::jsonb"
    return f"jsonb_strip_nulls(jsonb_build_object({', '.join(pairs)}))"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = %s
        )
        """,
        (table_name,),
    )
    return bool(cursor.fetchone()[0])


def table_columns(cursor, table_name: str) -> list[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [row[0] for row in cursor.fetchall()]


def column_type_map(cursor, table_name: str) -> dict[str, str]:
    cursor.execute(
        """
        SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relname = %s
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (table_name,),
    )
    return {name: data_type for name, data_type in cursor.fetchall()}


class Command(BaseCommand):
    help = "Nightly Skagit County assessor download, diff, upsert, and report."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=COUNTY_ZIP_URL, help="Skagit County assessor ZIP URL.")
        parser.add_argument("--local", metavar="ZIP_PATH", help="Use a local ZIP instead of downloading.")
        parser.add_argument(
            "--report-dir",
            default=str(settings.BASE_DIR / "output" / "assessor_sync_reports"),
            help="Directory for Markdown reports. The report is also stored in Postgres.",
        )
        parser.add_argument(
            "--audit-retain-runs",
            type=int,
            default=14,
            help="Keep row-level assessor_sync_changes for this many latest successful runs.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("sync_assessor_data requires PostgreSQL/PostGIS; the current database is not PostgreSQL.")

        report_dir = Path(options["report_dir"]).expanduser().resolve()
        report_dir.mkdir(parents=True, exist_ok=True)

        lock_acquired = False
        run_id: int | None = None
        started = datetime.now(UTC)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(hashtext('openskagit.sync_assessor_data'))")
                lock_acquired = bool(cursor.fetchone()[0])
                if not lock_acquired:
                    raise CommandError("Another assessor sync is already running.")

                self._ensure_sync_tables(cursor)
                run_id = self._start_run(cursor, options["url"] if not options["local"] else options["local"])

            with tempfile.TemporaryDirectory(prefix="openskagit_assessor_sync_") as tmp:
                zip_path = self._obtain_zip(Path(tmp), options)
                zip_hash = sha256_file(zip_path)
                self.stdout.write(f"Using {zip_path.name} ({zip_path.stat().st_size // 1024:,} KB)")

                with connection.cursor() as cursor:
                    file_changes = self._record_file_hashes(cursor, run_id, zip_path)

                with transaction.atomic():
                    with connection.cursor() as cursor:
                        stats = self._sync_zip(cursor, run_id, zip_path)

                finished = datetime.now(UTC)
                summary = {
                    "zip_sha256": zip_hash,
                    "started_at": started.isoformat(),
                    "finished_at": finished.isoformat(),
                    "files_changed": sum(1 for item in file_changes if item["changed"]),
                    "tables": stats,
                }

                report = self._build_report(run_id, started, finished, summary, file_changes)
                report_path = report_dir / f"assessor_sync_{finished.strftime('%Y%m%d_%H%M%S')}_run_{run_id}.md"
                report_path.write_text(report, encoding="utf-8")

                with connection.cursor() as cursor:
                    report_id = self._finish_run(cursor, run_id, "success", zip_hash, summary, str(report_path), report)

                narrative_status = self._create_parcel_book_narrative(report_id)

                self.stdout.write(report)
                if narrative_status:
                    self.stdout.write(narrative_status)
                with connection.cursor() as cursor:
                    pruned_changes = self._prune_sync_changes(cursor, int(options["audit_retain_runs"]), run_id)
                if pruned_changes:
                    self.stdout.write(self.style.WARNING(f"Pruned {pruned_changes:,} old assessor sync audit row(s)."))
                self.stdout.write(self.style.SUCCESS(f"Assessor sync complete. Report: {report_path}"))
        except Exception as exc:
            if run_id is not None:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE assessor_sync_runs
                        SET finished_at = now(), status = 'failed', error = %s
                        WHERE id = %s
                        """,
                        (str(exc), run_id),
                    )
            raise
        finally:
            if lock_acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext('openskagit.sync_assessor_data'))")
            connection.close()

    def _obtain_zip(self, tmp_dir: Path, options: dict) -> Path:
        if options["local"]:
            zip_path = Path(options["local"]).expanduser().resolve()
            if not zip_path.exists():
                raise CommandError(f"File not found: {zip_path}")
            return zip_path

        target = tmp_dir / "SkagitAssessmentData.zip"
        self.stdout.write(f"Downloading {options['url']}")
        urllib.request.urlretrieve(options["url"], target)
        return target

    def _ensure_sync_tables(self, cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS assessor_sync_runs (
                id BIGSERIAL PRIMARY KEY,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                finished_at TIMESTAMPTZ,
                source_url TEXT,
                zip_sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                report_path TEXT,
                summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                error TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS assessor_sync_files (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL REFERENCES assessor_sync_runs(id) ON DELETE CASCADE,
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                byte_size BIGINT NOT NULL,
                changed BOOLEAN NOT NULL,
                previous_sha256 TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS assessor_sync_changes (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL REFERENCES assessor_sync_runs(id) ON DELETE CASCADE,
                table_name TEXT NOT NULL,
                record_key TEXT NOT NULL,
                change_type TEXT NOT NULL,
                changed_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
                old_row JSONB,
                new_row JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS assessor_sync_reports (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL REFERENCES assessor_sync_runs(id) ON DELETE CASCADE,
                report_text TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assessor_sync_files_file_name ON assessor_sync_files (file_name, id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assessor_sync_changes_run_table ON assessor_sync_changes (run_id, table_name, change_type)")

    def _start_run(self, cursor, source_url: str) -> int:
        cursor.execute(
            "INSERT INTO assessor_sync_runs (source_url) VALUES (%s) RETURNING id",
            (source_url,),
        )
        return int(cursor.fetchone()[0])

    def _finish_run(
        self,
        cursor,
        run_id: int,
        status: str,
        zip_hash: str,
        summary: dict,
        report_path: str,
        report: str,
    ) -> int:
        cursor.execute(
            """
            UPDATE assessor_sync_runs
            SET finished_at = now(),
                status = %s,
                zip_sha256 = %s,
                summary = %s::jsonb,
                report_path = %s
            WHERE id = %s
            """,
            (status, zip_hash, json.dumps(summary), report_path, run_id),
        )
        cursor.execute(
            "INSERT INTO assessor_sync_reports (run_id, report_text) VALUES (%s, %s) RETURNING id",
            (run_id, report),
        )
        return int(cursor.fetchone()[0])

    def _create_parcel_book_narrative(self, report_id: int) -> str:
        try:
            from opportunity.services import generate_sync_narrative_for_report

            narrative = generate_sync_narrative_for_report(report_id, force=True)
            if narrative.generated_by_ai:
                return self.style.SUCCESS(f"Parcel Book narrative created with {narrative.model}.")
            if narrative.error:
                return self.style.WARNING(f"Parcel Book fallback narrative stored: {narrative.error}")
            return self.style.WARNING("Parcel Book fallback narrative stored.")
        except Exception as exc:
            return self.style.WARNING(f"Parcel Book narrative skipped: {exc}")

    def _record_file_hashes(self, cursor, run_id: int, zip_path: Path) -> list[dict]:
        cursor.execute(
            """
            SELECT DISTINCT ON (f.file_name) f.file_name, f.sha256
            FROM assessor_sync_files f
            JOIN assessor_sync_runs r ON r.id = f.run_id
            WHERE r.status = 'success'
            ORDER BY f.file_name, f.id DESC
            """
        )
        previous = dict(cursor.fetchall())

        rows = []
        with zipfile.ZipFile(zip_path) as zf:
            for info in sorted(zf.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                data = zf.read(info.filename)
                digest = sha256_bytes(data)
                prior = previous.get(info.filename)
                rows.append(
                    {
                        "file_name": info.filename,
                        "sha256": digest,
                        "byte_size": len(data),
                        "changed": prior != digest,
                        "previous_sha256": prior,
                    }
                )

        cursor.executemany(
            """
            INSERT INTO assessor_sync_files
                (run_id, file_name, sha256, byte_size, changed, previous_sha256)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (run_id, row["file_name"], row["sha256"], row["byte_size"], row["changed"], row["previous_sha256"])
                for row in rows
            ],
        )
        return rows

    def _sync_zip(self, cursor, run_id: int, zip_path: Path) -> dict:
        stats: dict[str, dict] = {}
        stage_tables: list[str] = []

        with zipfile.ZipFile(zip_path) as zf:
            members = set(zf.namelist())
            missing = [table.member_name for table in TABLES if table.member_name not in members]
            if missing:
                raise CommandError(f"ZIP is missing required assessor files: {', '.join(missing)}")

            self.stdout.write("Refreshing code descriptions and mappings")
            _import_code_descriptions(cursor, zf)
            _seed_code_mappings(cursor)
            _seed_primary_use_codes(cursor)
            mappings = _load_mappings(cursor)

            for table in TABLES:
                stage = f"assessor_sync_stage_{table.table}"
                stage_tables.append(stage)
                self.stdout.write(f"Staging {table.table}")
                row_count, warnings = _import_dataset(
                    cursor,
                    zf,
                    table.member_name,
                    table.table,
                    mappings,
                    self.stdout.write,
                    target_table_name=stage,
                )

                table_stats = self._sync_table(cursor, run_id, table, stage)
                table_stats["staged_rows"] = row_count
                table_stats["warnings"] = warnings
                stats[table.table] = table_stats

        for stage in stage_tables:
            if table_exists(cursor, stage):
                cursor.execute(f"DROP TABLE IF EXISTS {quote_ident(stage)} CASCADE")

        return stats

    def _sync_table(self, cursor, run_id: int, table: TableSync, stage: str) -> dict:
        target = table.table
        self._validate_key_columns(cursor, stage, table.key_columns)

        if not table_exists(cursor, target):
            inserted = self._record_all_stage_rows(cursor, run_id, table, stage, table_columns(cursor, stage))
            cursor.execute(f"ALTER TABLE {quote_ident(stage)} RENAME TO {quote_ident(target)}")
            return {"inserted": inserted, "updated": 0, "promoted": True}

        self._sync_target_columns(cursor, target, stage)

        target_columns = table_columns(cursor, target)
        stage_columns = table_columns(cursor, stage)
        excluded_target_columns = [col for col in target_columns if col not in stage_columns]
        audit_excluded_columns = self._audit_excluded_columns(table, excluded_target_columns)
        insert_columns = [col for col in stage_columns if col != "id" and col in target_columns]

        inserted, updated = self._create_changed_key_table(cursor, table, stage, audit_excluded_columns)
        self._record_new_rows(cursor, run_id, table, stage, stage_columns)
        self._record_changed_rows(cursor, run_id, table, stage, audit_excluded_columns)
        applied = self._apply_new_and_changed_rows(cursor, table, stage, insert_columns, excluded_target_columns)
        cursor.execute("DROP TABLE IF EXISTS tmp_assessor_sync_keys")

        return {"inserted": inserted, "updated": updated, "applied_rows": applied, "promoted": False}

    def _audit_excluded_columns(self, table: TableSync, excluded_target_columns: Iterable[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*excluded_target_columns, *sorted(AUDIT_EXCLUDED_COLUMNS.get(table.table, set()))]))

    def _validate_key_columns(self, cursor, table_name: str, key_columns: tuple[str, ...]) -> None:
        columns = set(table_columns(cursor, table_name))
        missing = [column for column in key_columns if column not in columns]
        if missing:
            raise CommandError(f"{table_name} is missing key column(s): {', '.join(missing)}")

    def _sync_target_columns(self, cursor, target: str, stage: str) -> None:
        target_columns = set(table_columns(cursor, target))
        stage_types = column_type_map(cursor, stage)
        for column, data_type in stage_types.items():
            if column not in target_columns:
                cursor.execute(
                    f"ALTER TABLE {quote_ident(target)} ADD COLUMN {quote_ident(column)} {data_type}"
                )

    def _record_all_stage_rows(
        self,
        cursor,
        run_id: int,
        table: TableSync,
        stage: str,
        stage_columns: list[str],
    ) -> int:
        compact_new_row = compact_row_json_expr("s", table.table, stage_columns)
        cursor.execute(
            f"""
            INSERT INTO assessor_sync_changes
                (run_id, table_name, record_key, change_type, changed_fields, old_row, new_row)
            SELECT
                %s,
                %s,
                {key_expr("s", table.key_columns)} AS record_key,
                'insert',
                '{{}}'::jsonb,
                NULL,
                {compact_new_row}
            FROM {quote_ident(stage)} s
            WHERE {key_expr("s", table.key_columns)} <> ''
            """,
            (run_id, table.table),
        )
        return cursor.rowcount

    def _create_changed_key_table(
        self,
        cursor,
        table: TableSync,
        stage: str,
        excluded_target_columns: list[str],
    ) -> tuple[int, int]:
        cursor.execute("DROP TABLE IF EXISTS tmp_assessor_sync_keys")
        cursor.execute(
            """
            CREATE TEMP TABLE tmp_assessor_sync_keys (
                record_key TEXT NOT NULL,
                change_type TEXT NOT NULL
            ) ON COMMIT DROP
            """
        )

        target_hashes = self._combined_row_hashes(cursor, table.table, "t", table.key_columns, excluded_target_columns)
        stage_hashes = self._combined_row_hashes(cursor, stage, "s", table.key_columns, excluded_target_columns)

        changed_keys: list[tuple[str, str]] = []
        inserted = 0
        updated = 0
        for record_key, stage_hash in stage_hashes.items():
            target_hash = target_hashes.get(record_key)
            if target_hash is None:
                changed_keys.append((record_key, "insert"))
                inserted += 1
            elif target_hash != stage_hash:
                changed_keys.append((record_key, "update"))
                updated += 1

        if changed_keys:
            cursor.executemany(
                "INSERT INTO tmp_assessor_sync_keys (record_key, change_type) VALUES (%s, %s)",
                changed_keys,
            )
        cursor.execute("CREATE INDEX tmp_assessor_sync_keys_key_idx ON tmp_assessor_sync_keys (record_key)")
        return inserted, updated

    def _combined_row_hashes(
        self,
        cursor,
        table_name: str,
        alias: str,
        key_columns: tuple[str, ...],
        excluded_columns: Iterable[str],
    ) -> dict[str, str]:
        key_sql = key_expr(alias, key_columns)
        row_sql = row_json_expr(alias, excluded_columns)
        cursor.execute(
            f"""
            SELECT {key_sql} AS record_key, md5(({row_sql})::text) AS row_hash
            FROM {quote_ident(table_name)} {alias}
            WHERE {key_sql} <> ''
            """,
        )

        grouped: dict[str, list[str]] = {}
        while True:
            rows = cursor.fetchmany(5000)
            if not rows:
                break
            for record_key, row_hash in rows:
                grouped.setdefault(record_key, []).append(row_hash)

        return {
            record_key: hashlib.md5(",".join(sorted(row_hashes)).encode("utf-8")).hexdigest()
            for record_key, row_hashes in grouped.items()
        }

    def _record_new_rows(
        self,
        cursor,
        run_id: int,
        table: TableSync,
        stage: str,
        stage_columns: list[str],
    ) -> int:
        stage_key = key_expr("s", table.key_columns)
        compact_new_row = compact_row_json_expr("s", table.table, stage_columns)
        cursor.execute(
            f"""
            INSERT INTO assessor_sync_changes
                (run_id, table_name, record_key, change_type, changed_fields, old_row, new_row)
            SELECT
                %s,
                %s,
                {stage_key},
                'insert',
                '{{}}'::jsonb,
                NULL,
                {compact_new_row}
            FROM {quote_ident(stage)} s
            JOIN tmp_assessor_sync_keys k
              ON k.record_key = {stage_key}
             AND k.change_type = 'insert'
            """,
            (run_id, table.table),
        )
        return cursor.rowcount

    def _record_changed_rows(
        self,
        cursor,
        run_id: int,
        table: TableSync,
        stage: str,
        excluded_target_columns: list[str],
    ) -> int:
        stage_key = key_expr("s", table.key_columns)
        target_key = key_expr("t", table.key_columns)
        old_row = row_json_expr("t", excluded_target_columns)
        new_row = row_json_expr("s")
        cursor.execute(
            f"""
            WITH pairs AS (
                SELECT
                    {stage_key} AS record_key,
                    {old_row} AS old_row,
                    {new_row} AS new_row
                FROM {quote_ident(stage)} s
                JOIN {quote_ident(table.table)} t
                  ON {target_key} = {stage_key}
                JOIN tmp_assessor_sync_keys k
                  ON k.record_key = {stage_key}
                 AND k.change_type = 'update'
                WHERE {stage_key} <> ''
            ),
            diffs AS (
                SELECT record_key, old_row, new_row
                FROM pairs
                WHERE old_row IS DISTINCT FROM new_row
            )
            INSERT INTO assessor_sync_changes
                (run_id, table_name, record_key, change_type, changed_fields, old_row, new_row)
            SELECT
                %s,
                %s,
                record_key,
                'update',
                COALESCE((
                    SELECT jsonb_object_agg(
                        COALESCE(o.key, n.key),
                        jsonb_build_object('old', o.value, 'new', n.value)
                    )
                    FROM jsonb_each(old_row) o
                    FULL OUTER JOIN jsonb_each(new_row) n ON n.key = o.key
                    WHERE o.value IS DISTINCT FROM n.value
                ), '{{}}'::jsonb),
                NULL,
                NULL
            FROM diffs
            """,
            (run_id, table.table),
        )
        return cursor.rowcount

    def _apply_new_and_changed_rows(
        self,
        cursor,
        table: TableSync,
        stage: str,
        insert_columns: list[str],
        excluded_target_columns: list[str],
    ) -> int:
        if not insert_columns:
            return 0

        stage_key = key_expr("s", table.key_columns)
        target_key = key_expr("t", table.key_columns)
        old_row = row_json_expr("t", excluded_target_columns)
        new_row = row_json_expr("s")

        cursor.execute(
            f"""
            DELETE FROM {quote_ident(table.table)} t
            USING tmp_assessor_sync_keys k
            WHERE {target_key} = k.record_key
            """
        )

        column_list = ", ".join(quote_ident(column) for column in insert_columns)
        select_list = ", ".join(f"s.{quote_ident(column)}" for column in insert_columns)
        cursor.execute(
            f"""
            INSERT INTO {quote_ident(table.table)} ({column_list})
            SELECT {select_list}
            FROM {quote_ident(stage)} s
            JOIN tmp_assessor_sync_keys k
              ON {stage_key} = k.record_key
            """
        )
        applied = cursor.rowcount
        cursor.execute("DROP TABLE IF EXISTS tmp_assessor_sync_keys")
        return applied

    def _prune_sync_changes(self, cursor, retain_success_runs: int, current_run_id: int) -> int:
        if retain_success_runs < 1:
            retain_success_runs = 1
        cursor.execute(
            """
            WITH retained_runs AS (
                SELECT id
                FROM assessor_sync_runs
                WHERE status = 'success'
                ORDER BY started_at DESC, id DESC
                LIMIT %s
            )
            DELETE FROM assessor_sync_changes c
            WHERE c.run_id <> %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM retained_runs r
                  WHERE r.id = c.run_id
              )
            """,
            (retain_success_runs, current_run_id),
        )
        return cursor.rowcount

    def _build_report(
        self,
        run_id: int,
        started: datetime,
        finished: datetime,
        summary: dict,
        file_changes: list[dict],
    ) -> str:
        lines = [
            "# Skagit Assessor Sync Report",
            "",
            f"Run: {run_id}",
            f"Started: {started.isoformat()}",
            f"Finished: {finished.isoformat()}",
            "",
            "## Summary",
            "",
        ]
        for table in TABLES:
            stats = summary["tables"].get(table.table, {})
            lines.append(
                f"- {table.report_label}: {stats.get('inserted', 0):,} new, "
                f"{stats.get('updated', 0):,} changed, {stats.get('staged_rows', 0):,} rows checked"
            )

        changed_files = [row for row in file_changes if row["changed"]]
        lines.extend(["", "## Files Changed Since Last Run", ""])
        if changed_files:
            for row in changed_files:
                prior = row["previous_sha256"][:12] if row["previous_sha256"] else "none"
                lines.append(f"- {row['file_name']} ({row['byte_size']:,} bytes, previous {prior})")
        else:
            lines.append("- No downloaded files changed.")

        lines.extend(self._report_samples(run_id, "sales", "insert", "New Sales Appeared"))
        lines.extend(self._report_samples(run_id, "assessor_rollup", "insert", "New Parcels Appeared"))
        lines.extend(self._report_samples(run_id, "assessor_rollup", "update", "Parcel Records Changed"))
        lines.extend(self._report_samples(run_id, "land", "update", "Land Records Changed"))
        lines.extend(self._report_samples(run_id, "improvements", "update", "Improvement Records Changed"))
        return "\n".join(lines) + "\n"

    def _report_samples(self, run_id: int, table_name: str, change_type: str, title: str) -> list[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT record_key, changed_fields, new_row
                FROM assessor_sync_changes
                WHERE run_id = %s
                  AND table_name = %s
                  AND change_type = %s
                ORDER BY id
                LIMIT %s
                """,
                (run_id, table_name, change_type, REPORT_ROW_LIMIT),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT count(*)
                FROM assessor_sync_changes
                WHERE run_id = %s
                  AND table_name = %s
                  AND change_type = %s
                """,
                (run_id, table_name, change_type),
            )
            total = cursor.fetchone()[0]

        lines = ["", f"## {title}", ""]
        if not rows:
            lines.append("- None.")
            return lines

        lines.append(f"Showing {len(rows):,} of {total:,}. Compact signal details are stored in assessor_sync_changes.")
        for record_key, changed_fields, new_row in rows:
            lines.append(f"- {record_key}: {self._sample_detail(table_name, change_type, changed_fields, new_row)}")
        return lines

    def _sample_detail(self, table_name: str, change_type: str, changed_fields, new_row) -> str:
        if isinstance(changed_fields, str):
            changed_fields = json.loads(changed_fields)
        if isinstance(new_row, str):
            new_row = json.loads(new_row)

        if change_type == "update":
            fields = ", ".join(sorted(changed_fields.keys())[:12])
            extra = "" if len(changed_fields) <= 12 else f", +{len(changed_fields) - 12} more"
            return f"changed fields: {fields}{extra}"

        if table_name == "sales":
            return (
                f"{new_row.get('sale_date_iso') or new_row.get('sale_date') or 'unknown date'}, "
                f"${new_row.get('sale_price') or new_row.get('sale_price_num') or 'unknown'}, "
                f"{new_row.get('seller_name') or 'unknown seller'} to {new_row.get('buyer_name') or 'unknown buyer'}"
            )
        if table_name == "assessor_rollup":
            address = " ".join(
                part for part in [
                    new_row.get("situs_street_number"),
                    new_row.get("situs_street_name"),
                    new_row.get("situs_city_state_zip"),
                ]
                if part
            )
            return f"{new_row.get('owner_name') or 'unknown owner'}; {address or 'no situs address'}"
        return f"{len(new_row)} fields"
