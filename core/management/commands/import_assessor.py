"""
Django management command: import_assessor

Downloads and imports Skagit County assessor data into Postgres.

Usage:
    python manage.py import_assessor --remote          # download from county
    python manage.py import_assessor --local path.zip  # use local ZIP file
"""
from __future__ import annotations

import csv
import io
import os
import re
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

COUNTY_ZIP_URL = "https://www.skagitcounty.net/Assessor/Documents/DataDownloads/SkagitAssessmentData.zip"

DATASETS = {
    "assessor_rollup": "AssessorData.txt",
    "improvements":    "Improvements.txt",
    "land":            "Land.txt",
    "sales":           "Sales.txt",
}


# ── Column name helpers ────────────────────────────────────────────────────────

def slugify_column(name: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip().lower()).strip("_")
    if not value:
        value = "column"
    if value[0].isdigit():
        value = f"col_{value}"
    return value


def unique_columns(headers: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    cols: list[str] = []
    for header in headers:
        base = slugify_column(header)
        count = seen.get(base, 0)
        seen[base] = count + 1
        cols.append(base if count == 0 else f"{base}_{count + 1}")
    return cols


# ── Value parsers (pure Python — no framework deps) ───────────────────────────

def parse_parenthesized_code(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    match = re.match(r"\(([^)]+)\)\s*(.*)", value.strip())
    if not match:
        return None, value.strip()
    return match.group(1).strip(), match.group(2).strip()


def parse_land_use(value: str | None) -> tuple[str | None, str | None]:
    return parse_parenthesized_code(value)


def clean_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def normalize_utility_code(value: str | None) -> str | None:
    cleaned = clean_code(value)
    if not cleaned:
        return None
    cleaned = cleaned.strip("*'")
    cleaned = cleaned.replace("�", "-").replace("_", "-")
    cleaned = re.sub(r"[^A-Z0-9]+", "-", cleaned).strip("-")
    return cleaned or None


def parse_utility_codes(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = value.strip().strip("*'")
    cleaned = cleaned.replace(".", ",").replace(";", ",")
    tokens = [normalize_utility_code(part) for part in re.split(r"[,\s]+", cleaned) if part.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().replace(",", "")
    if cleaned == "":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()[:10]
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None
    if parsed.year < 1800 or parsed.year > datetime.now(UTC).year + 1:
        return None
    return parsed.date().isoformat()


# ── Table schema helpers ───────────────────────────────────────────────────────

def _extra_columns(table_name: str) -> list[tuple[str, str]]:
    if table_name == "assessor_rollup":
        return [
            ("land_use_code", "TEXT"),
            ("land_use_description", "TEXT"),
            ("neighborhood_code_id", "TEXT"),
            ("neighborhood_description", "TEXT"),
            ("utilities_codes", "TEXT"),
            ("utilities_description", "TEXT"),
            ("assessed_value_num", "REAL"),
            ("taxable_value_num", "REAL"),
            ("total_market_value_num", "REAL"),
            ("acres_num", "REAL"),
            ("sale_price_num", "REAL"),
            ("sale_date_iso", "TEXT"),
        ]
    if table_name == "sales":
        return [("sale_price_num", "REAL"), ("sale_date_iso", "TEXT"), ("deed_date_iso", "TEXT")]
    if table_name == "land":
        return [("size_acres_num", "REAL"), ("market_value_num", "REAL")]
    if table_name == "improvements":
        return [
            ("imprv_det_type_description", "TEXT"),
            ("imprv_det_class_description", "TEXT"),
            ("condition_description", "TEXT"),
            ("imprv_val_num", "REAL"),
            ("living_area_num", "REAL"),
        ]
    return []


def _normalized_values(
    table_name: str,
    columns: list[str],
    values: list[str | None],
    mappings: dict[str, dict[str, str]],
) -> list[object | None]:
    row = dict(zip(columns, values))
    if table_name == "assessor_rollup":
        code, desc = parse_land_use(row.get("land_use"))
        neighborhood_code, neighborhood_desc = parse_parenthesized_code(row.get("neighborhood_code"))
        utility_codes = parse_utility_codes(row.get("utilities"))
        utility_descriptions = [mappings.get("utilities", {}).get(c, c) for c in utility_codes]
        return [
            code, desc,
            neighborhood_code, neighborhood_desc,
            ", ".join(utility_codes) if utility_codes else None,
            ", ".join(utility_descriptions) if utility_descriptions else None,
            to_float(row.get("assessed_value")),
            to_float(row.get("taxable_value")),
            to_float(row.get("total_market_value")),
            to_float(row.get("acres")),
            to_float(row.get("sale_price")),
            normalize_date(row.get("sale_date")),
        ]
    if table_name == "sales":
        return [
            to_float(row.get("sale_price")),
            normalize_date(row.get("sale_date")),
            normalize_date(row.get("deed_date")),
        ]
    if table_name == "land":
        return [to_float(row.get("size_acres")), to_float(row.get("market_value"))]
    if table_name == "improvements":
        type_code = clean_code(row.get("imprv_det_type_cd"))
        class_code = clean_code(row.get("imprv_det_class_cd"))
        condition_code = clean_code(row.get("condition_cd"))
        return [
            mappings.get("improvement_type", {}).get(type_code) if type_code else None,
            mappings.get("improvement_class", {}).get(class_code) if class_code else None,
            mappings.get("condition", {}).get(condition_code) if condition_code else None,
            to_float(row.get("imprv_val")),
            to_float(row.get("tot_living_area")),
        ]
    return []


# ── Row reader (handles malformed/multi-line CSV rows) ────────────────────────

@dataclass
class LogicalRow:
    values: list[str | None]
    raw: str
    warning: str | None = None


def _logical_rows(
    reader: csv.reader,
    column_count: int,
    table_name: str,
) -> Iterable[tuple[int, LogicalRow]]:
    current: list[str] | None = None
    current_line = 1
    current_warning: str | None = None

    def flush():
        nonlocal current, current_line, current_warning
        if current is None:
            return None
        result = (
            current_line,
            LogicalRow(
                current[:column_count],
                "|".join("" if v is None else str(v) for v in current),
                current_warning,
            ),
        )
        current = None
        current_warning = None
        return result

    for line_number, row in enumerate(reader, start=2):
        if len(row) == column_count:
            pending = flush()
            if pending:
                yield pending
            current = row
            current_line = line_number
        elif len(row) > column_count:
            pending = flush()
            if pending:
                yield pending
            repaired = row[: column_count - 1] + ["|".join(row[column_count - 1:])]
            current = repaired
            current_line = line_number
            current_warning = f"Repaired row with {len(row)} fields by joining extras into final field."
        elif current is not None and table_name == "land":
            current[-1] = (current[-1] or "") + ("\n" if row else "\n") + "|".join(row)
            current_warning = "Repaired embedded newline in land segment comment."
        elif len(row) == 0:
            continue
        else:
            padded = row + [None] * (column_count - len(row))
            pending = flush()
            if pending:
                yield pending
            current = padded
            current_line = line_number
            current_warning = f"Padded malformed row with {len(row)} fields."

    pending = flush()
    if pending:
        yield pending


# ── Postgres DDL + import ──────────────────────────────────────────────────────

def _create_or_replace_table(cursor, table_name: str, columns: list[str], extras: list[tuple[str, str]]) -> None:
    cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
    raw_cols = ", ".join(f'"{col}" TEXT' for col in columns)
    extra_cols = ", ".join(f'"{name}" {kind}' for name, kind in extras)
    sep = ", " if extra_cols else ""
    cursor.execute(
        f'CREATE TABLE "{table_name}" (id BIGSERIAL PRIMARY KEY, {raw_cols}{sep}{extra_cols})'
    )


def _create_indexes(
    cursor,
    table_name: str,
    columns: set[str],
    logical_table_name: str | None = None,
) -> None:
    index_map = {
        "assessor_rollup": ["parcel_number", "owner_name", "situs_street_name", "land_use_code", "neighborhood_code"],
        "sales":           ["parcel_number", "sale_date_iso"],
        "land":            ["parcelnumber"],
        "improvements":    ["parcelnumber"],
    }
    for col in index_map.get(logical_table_name or table_name, []):
        if col not in columns:
            continue
        cursor.execute(
            f'CREATE INDEX "idx_{table_name}_{col}" ON "{table_name}" ("{col}")'
        )


def _import_dataset(
    cursor,
    zf: zipfile.ZipFile,
    member_name: str,
    table_name: str,
    mappings: dict,
    log,
    target_table_name: str | None = None,
) -> tuple[int, int]:
    physical_table_name = target_table_name or table_name
    with zf.open(member_name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        reader = csv.reader(text, delimiter="|")
        source_headers = next(reader)
        columns = unique_columns(source_headers)
        extras = _extra_columns(table_name)

        _create_or_replace_table(cursor, physical_table_name, columns, extras)

        insert_cols = columns + [name for name, _ in extras]
        placeholders = ", ".join("%s" for _ in insert_cols)
        quoted_cols = ", ".join(f'"{c}"' for c in insert_cols)
        sql = f'INSERT INTO "{physical_table_name}" ({quoted_cols}) VALUES ({placeholders})'

        count = 0
        warnings = 0
        batch: list[list] = []

        for _line_number, row in _logical_rows(reader, len(columns), table_name):
            if row.warning:
                warnings += 1
            extra_values = _normalized_values(table_name, columns, row.values, mappings)
            batch.append(row.values + extra_values)
            count += 1
            if len(batch) >= 2000:
                cursor.executemany(sql, batch)
                batch.clear()
                log(f"  {table_name}: {count} rows…")
        if batch:
            cursor.executemany(sql, batch)

        _create_indexes(cursor, physical_table_name, set(insert_cols), logical_table_name=table_name)
        return count, warnings


def _import_code_descriptions(cursor, zf: zipfile.ZipFile) -> int:
    cursor.execute("DROP TABLE IF EXISTS code_descriptions CASCADE")
    cursor.execute(
        """
        CREATE TABLE code_descriptions (
            id BIGSERIAL PRIMARY KEY,
            source_file TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT NOT NULL
        )
        """
    )
    rows: list[tuple[str, str, str]] = []
    for name in zf.namelist():
        if not name.startswith("CodeDescriptions/") or not name.lower().endswith(".csv"):
            continue
        with zf.open(name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            reader = csv.reader(text)
            next(reader, None)
            for row in reader:
                if len(row) >= 2 and row[0].strip():
                    rows.append((Path(name).name, row[0].strip(), row[1].strip()))
    cursor.executemany(
        "INSERT INTO code_descriptions (source_file, code, description) VALUES (%s, %s, %s)",
        rows,
    )
    return len(rows)


def _seed_code_mappings(cursor) -> int:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS code_mappings (
            id BIGSERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(category, code)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_code_mappings_category
        ON code_mappings (category, code)
        """
    )

    seeds: list[tuple[str, str, str, str]] = []

    def from_code_descriptions(category: str, source_file: str, normalizer=clean_code):
        cursor.execute(
            "SELECT code, description FROM code_descriptions WHERE source_file = %s",
            (source_file,),
        )
        for code_raw, description in cursor.fetchall():
            code = normalizer(code_raw)
            description = (description or "").strip()
            if code and description:
                seeds.append((category, code, description, source_file))

    from_code_descriptions("improvement_type",  "impsegtype.csv")
    from_code_descriptions("improvement_class", "impsegclass.csv")
    from_code_descriptions("land_use",          "landuse.csv")
    from_code_descriptions("neighborhood",      "neighborhood.csv")
    from_code_descriptions("utilities",         "utilities.csv", normalize_utility_code)

    built_in = [
        ("condition", "E",    "Excellent",          "built-in"),
        ("condition", "VG",   "Very good",          "built-in"),
        ("condition", "G",    "Good",               "built-in"),
        ("condition", "A",    "Average",            "built-in"),
        ("condition", "F",    "Fair",               "built-in"),
        ("condition", "L",    "Low",                "built-in"),
        ("condition", "P",    "Poor",               "built-in"),
        ("condition", "*",    "Unknown",            "built-in"),
        ("improvement_class", "MSA",  "Average",    "built-in"),
        ("improvement_class", "MSG",  "Good",       "built-in"),
        ("improvement_class", "MSVG", "Very good",  "built-in"),
        ("improvement_class", "MSE",  "Excellent",  "built-in"),
        ("improvement_class", "MSF",  "Fair",       "built-in"),
        ("improvement_class", "MSL",  "Low",        "built-in"),
        ("improvement_type",  "AGAR", "Attached garage",         "built-in"),
        ("improvement_type",  "CCP",  "Covered concrete porch",  "built-in"),
        ("improvement_type",  "CWP",  "Covered wood porch",      "built-in"),
        ("utilities", "PWR",   "Power",               "built-in"),
        ("utilities", "PWR-U", "Power underground",   "built-in"),
        ("utilities", "SEW",   "Sewer",               "built-in"),
        ("utilities", "SEP",   "Septic",              "built-in"),
        ("utilities", "WTR-P", "Public water",        "built-in"),
        ("utilities", "WTR-W", "Well water",          "built-in"),
        ("utilities", "NONE",  "No listed utilities", "built-in"),
    ]
    seeds.extend(built_in)

    cursor.executemany(
        """
        INSERT INTO code_mappings (category, code, description, source)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (category, code) DO NOTHING
        """,
        [(cat, code, desc, src) for cat, code, desc, src in seeds if code],
    )
    return len(seeds)


def _seed_primary_use_codes(cursor) -> int:
    cursor.execute("DROP TABLE IF EXISTS primary_use_codes CASCADE")
    cursor.execute(
        """
        CREATE TABLE primary_use_codes (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        "SELECT code, description FROM code_descriptions WHERE source_file = 'landuse.csv'"
    )
    rows = cursor.fetchall()
    cursor.executemany(
        """
        INSERT INTO primary_use_codes (code, description, source)
        VALUES (%s, %s, 'landuse.csv')
        ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description
        """,
        rows,
    )
    return len(rows)


def _load_mappings(cursor) -> dict[str, dict[str, str]]:
    cursor.execute("SELECT category, code, description FROM code_mappings")
    result: dict[str, dict[str, str]] = {}
    for category, code, description in cursor.fetchall():
        result.setdefault(category, {})[code] = description
    return result


# ── Main import orchestrator ───────────────────────────────────────────────────

def import_zip(zip_path: Path, source_url: str | None, log) -> dict:
    log(f"Importing from {zip_path.name}…")
    stats: dict[str, int] = {}

    with transaction.atomic():
        with connection.cursor() as cursor:
            with zipfile.ZipFile(zip_path) as zf:
                log("Importing code descriptions…")
                n = _import_code_descriptions(cursor, zf)
                log(f"  {n} code description rows")

                log("Seeding code mappings…")
                n = _seed_code_mappings(cursor)
                log(f"  {n} mapping rows seeded")

                log("Seeding primary use codes…")
                n = _seed_primary_use_codes(cursor)
                log(f"  {n} land use codes")

                mappings = _load_mappings(cursor)

                for table_name, member_name in DATASETS.items():
                    log(f"Importing {table_name}…")
                    count, warnings = _import_dataset(cursor, zf, member_name, table_name, mappings, log)
                    stats[table_name] = count
                    log(f"  {table_name}: {count} rows, {warnings} warnings")

    return stats


# ── Django Command ─────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Import Skagit County assessor data into Postgres"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--remote",
            action="store_true",
            help=f"Download ZIP from {COUNTY_ZIP_URL}",
        )
        group.add_argument(
            "--local",
            metavar="ZIP_PATH",
            help="Path to a local SkagitAssessmentData.zip file",
        )
        parser.add_argument(
            "--url",
            default=COUNTY_ZIP_URL,
            help="Override the county download URL (used with --remote)",
        )

    def handle(self, *args, **options):
        def log(msg: str) -> None:
            self.stdout.write(msg)

        if options["remote"]:
            url = options["url"]
            self.stdout.write(f"Downloading from {url}…")
            with tempfile.TemporaryDirectory(prefix="openskagit_dl_") as tmp:
                target = Path(tmp) / "SkagitAssessmentData.zip"
                urllib.request.urlretrieve(url, target)
                self.stdout.write(f"Downloaded to {target} ({target.stat().st_size // 1024} KB)")
                stats = import_zip(target, source_url=url, log=log)
        else:
            zip_path = Path(options["local"]).expanduser().resolve()
            if not zip_path.exists():
                raise CommandError(f"File not found: {zip_path}")
            stats = import_zip(zip_path, source_url=None, log=log)

        self.stdout.write(self.style.SUCCESS("\nImport complete:"))
        for table, count in stats.items():
            self.stdout.write(f"  {table}: {count:,} rows")
