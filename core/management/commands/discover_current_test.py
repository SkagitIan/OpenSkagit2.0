from __future__ import annotations

import json
import os
from decimal import Decimal
from getpass import getpass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


PROBE_VALUE_PER_ACRE_OUTLIERS = "value_per_acre_outliers"
PROBE_LAND_IMPROVEMENT_IMBALANCE = "land_vs_improvement_imbalance"
PROBE_ZONING_LAND_USE_MISMATCH = "zoning_land_use_mismatch"
PROBE_SALE_ASSESSMENT_GAP = "sale_assessment_gap"
SUPPORTED_PROBES = {
    PROBE_VALUE_PER_ACRE_OUTLIERS,
    PROBE_LAND_IMPROVEMENT_IMBALANCE,
    PROBE_ZONING_LAND_USE_MISMATCH,
    PROBE_SALE_ASSESSMENT_GAP,
}

PARCEL_TABLE = "assessor_rollup"
ZONING_TABLE = "parcel_primary_zoning"
LAND_TABLE = "land"
SALES_TABLE = "sales"
PROBE_CATALOG_PATH = Path("data") / "discovery_probes.json"

REQUIRED_PARCEL_COLUMNS = {
    "parcel_number",
    "situs_street_number",
    "situs_street_name",
    "situs_city_state_zip",
    "assessed_value_num",
    "building_value",
    "acres_num",
    "land_use_description",
}

ZONING_COLUMNS = {"parcel_id", "zone_name"}
ZONING_MISMATCH_COLUMNS = {"parcel_id", "zone_name", "waza_general"}
LAND_COLUMNS = {"parcelnumber", "market_value_num"}
SALES_COLUMNS = {"parcel_number", "sale_price_num", "sale_date_iso", "sale_type"}
ARTIFACT_LAND_USE_PATTERNS = (
    "water",
    "right",
    "row",
    "common",
    "condo",
    "utility",
)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def numeric_expression(sql_expression: str) -> str:
    return (
        "NULLIF("
        f"regexp_replace({sql_expression}::text, '[^0-9.-]', '', 'g'), "
        "''"
        ")::numeric"
    )


def fetch_columns() -> dict[str, set[str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
              AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            [[PARCEL_TABLE, ZONING_TABLE, LAND_TABLE, SALES_TABLE]],
        )
        rows = cursor.fetchall()

    columns: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        columns.setdefault(table_name, set()).add(column_name)
    return columns


def load_probe_catalog() -> dict[str, dict[str, Any]]:
    path = settings.BASE_DIR / PROBE_CATALOG_PATH
    if not path.exists():
        raise CommandError(f"Discovery probe catalog not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"Discovery probe catalog is not valid JSON: {exc}") from exc
    probes = payload.get("probes", [])
    if not isinstance(probes, list):
        raise CommandError("Discovery probe catalog must contain a probes list.")
    return {
        str(item.get("probe")): item
        for item in probes
        if isinstance(item, dict) and item.get("probe")
    }


def summarize_missing_columns(columns: dict[str, set[str]]) -> list[str]:
    missing: list[str] = []
    parcel_columns = columns.get(PARCEL_TABLE, set())
    if not parcel_columns:
        missing.append(f"{PARCEL_TABLE}: table not found")
    else:
        for column in sorted(REQUIRED_PARCEL_COLUMNS - parcel_columns):
            missing.append(f"{PARCEL_TABLE}.{column}")
    return missing


def build_value_per_acre_sql(columns: dict[str, set[str]], limit: int) -> str:
    parcel = quote_identifier(PARCEL_TABLE)
    parcel_columns = columns.get(PARCEL_TABLE, set())
    zoning_columns = columns.get(ZONING_TABLE, set())
    land_columns = columns.get(LAND_TABLE, set())

    assessed = 'p."assessed_value_num"::numeric'
    acres = 'p."acres_num"::numeric'
    improvement = numeric_expression('p."building_value"')

    joins: list[str] = []
    select_zoning = "NULL::text AS zoning"
    if ZONING_COLUMNS.issubset(zoning_columns):
        joins.append(
            'LEFT JOIN "parcel_primary_zoning" z '
            'ON z."parcel_id" = p."parcel_number"'
        )
        select_zoning = 'z."zone_name" AS zoning'

    if "impr_land_value" in parcel_columns:
        land_value = numeric_expression('p."impr_land_value"')
    elif LAND_COLUMNS.issubset(land_columns):
        joins.append(
            """
            LEFT JOIN (
                SELECT
                    "parcelnumber",
                    SUM("market_value_num"::numeric) AS market_value_num
                FROM "land"
                GROUP BY "parcelnumber"
            ) l ON l."parcelnumber" = p."parcel_number"
            """.strip()
        )
        land_value = 'l."market_value_num"::numeric'
    else:
        land_value = "NULL::numeric"

    address = (
        "concat_ws(' ', "
        "NULLIF(p.\"situs_street_number\", ''), "
        "NULLIF(p.\"situs_street_name\", ''), "
        "NULLIF(p.\"situs_city_state_zip\", '')"
        ")"
    )
    join_sql = "\n".join(joins)
    sql = f"""
        SELECT
            p."parcel_number" AS parcel_id,
            {address} AS address,
            {assessed} AS assessed_value,
            {land_value} AS land_value,
            {improvement} AS improvement_value,
            {acres} AS acres,
            {select_zoning},
            p."land_use_description" AS land_use,
            ({assessed} / NULLIF({acres}, 0)) AS value_per_acre,
            ({land_value} / NULLIF({improvement} + 1, 0)) AS land_to_improvement_ratio
        FROM {parcel} p
        {join_sql}
        WHERE {assessed} > 0
          AND {acres} >= 0.05
          AND {acres} <= 100
        ORDER BY value_per_acre DESC
        LIMIT {int(limit)}
    """
    return "\n".join(line.rstrip() for line in sql.strip().splitlines())


def build_land_improvement_imbalance_sql(columns: dict[str, set[str]], limit: int) -> str:
    parcel_columns = columns.get(PARCEL_TABLE, set())
    zoning_columns = columns.get(ZONING_TABLE, set())
    land_columns = columns.get(LAND_TABLE, set())
    assessed = 'p."assessed_value_num"::numeric'
    acres = 'p."acres_num"::numeric'
    improvement = numeric_expression('p."building_value"')
    joins: list[str] = []
    select_zoning = "NULL::text AS zoning"
    if ZONING_COLUMNS.issubset(zoning_columns):
        joins.append('LEFT JOIN "parcel_primary_zoning" z ON z."parcel_id" = p."parcel_number"')
        select_zoning = 'z."zone_name" AS zoning'
    if "impr_land_value" in parcel_columns:
        land_value = numeric_expression('p."impr_land_value"')
    elif LAND_COLUMNS.issubset(land_columns):
        joins.append(
            """
            LEFT JOIN (
                SELECT "parcelnumber", SUM("market_value_num"::numeric) AS market_value_num
                FROM "land"
                GROUP BY "parcelnumber"
            ) l ON l."parcelnumber" = p."parcel_number"
            """.strip()
        )
        land_value = 'l."market_value_num"::numeric'
    else:
        raise CommandError("land_vs_improvement_imbalance needs assessor_rollup.impr_land_value or land.market_value_num.")
    address = "concat_ws(' ', NULLIF(p.\"situs_street_number\", ''), NULLIF(p.\"situs_street_name\", ''), NULLIF(p.\"situs_city_state_zip\", ''))"
    sql = f"""
        SELECT
            p."parcel_number" AS parcel_id,
            {address} AS address,
            {assessed} AS assessed_value,
            {land_value} AS land_value,
            {improvement} AS improvement_value,
            {acres} AS acres,
            {select_zoning},
            p."land_use_description" AS land_use,
            ({land_value} / NULLIF({improvement} + 1, 0)) AS land_to_improvement_ratio
        FROM "assessor_rollup" p
        {" ".join(joins)}
        WHERE {assessed} > 0
          AND {acres} >= 0.05
          AND {land_value} > 0
          AND COALESCE({improvement}, 0) >= 0
        ORDER BY land_to_improvement_ratio DESC NULLS LAST
        LIMIT {int(limit)}
    """
    return "\n".join(line.rstrip() for line in sql.strip().splitlines())


def build_zoning_land_use_mismatch_sql(columns: dict[str, set[str]], limit: int) -> str:
    if not ZONING_MISMATCH_COLUMNS.issubset(columns.get(ZONING_TABLE, set())):
        missing = sorted(ZONING_MISMATCH_COLUMNS - columns.get(ZONING_TABLE, set()))
        raise CommandError("zoning_land_use_mismatch needs parcel_primary_zoning columns: " + ", ".join(missing))
    assessed = 'p."assessed_value_num"::numeric'
    acres = 'p."acres_num"::numeric'
    address = "concat_ws(' ', NULLIF(p.\"situs_street_number\", ''), NULLIF(p.\"situs_street_name\", ''), NULLIF(p.\"situs_city_state_zip\", ''))"
    sql = f"""
        SELECT
            p."parcel_number" AS parcel_id,
            {address} AS address,
            {assessed} AS assessed_value,
            {acres} AS acres,
            z."zone_name" AS zoning,
            z."waza_general" AS zoning_general,
            p."land_use_description" AS land_use,
            ({assessed} / NULLIF({acres}, 0)) AS value_per_acre
        FROM "assessor_rollup" p
        JOIN "parcel_primary_zoning" z ON z."parcel_id" = p."parcel_number"
        WHERE {assessed} > 0
          AND {acres} >= 0.05
          AND p."land_use_description" IS NOT NULL
          AND z."zone_name" IS NOT NULL
          AND (
              lower(z."zone_name") LIKE '%commercial%' AND lower(p."land_use_description") NOT LIKE '%commercial%'
              OR lower(z."zone_name") LIKE '%industrial%' AND lower(p."land_use_description") NOT LIKE '%industrial%'
              OR lower(z."zone_name") LIKE '%residential%' AND lower(p."land_use_description") NOT LIKE '%res%'
          )
        ORDER BY assessed_value DESC
        LIMIT {int(limit)}
    """
    return "\n".join(line.rstrip() for line in sql.strip().splitlines())


def build_sale_assessment_gap_sql(columns: dict[str, set[str]], limit: int) -> str:
    if not SALES_COLUMNS.issubset(columns.get(SALES_TABLE, set())):
        raise CommandError("sale_assessment_gap needs sales parcel_number, sale_price_num, sale_date_iso, and sale_type.")
    assessed = 'p."assessed_value_num"::numeric'
    acres = 'p."acres_num"::numeric'
    address = "concat_ws(' ', NULLIF(p.\"situs_street_number\", ''), NULLIF(p.\"situs_street_name\", ''), NULLIF(p.\"situs_city_state_zip\", ''))"
    sql = f"""
        SELECT
            p."parcel_number" AS parcel_id,
            {address} AS address,
            {assessed} AS assessed_value,
            s."sale_price_num"::numeric AS sale_price,
            s."sale_date_iso" AS sale_date,
            s."sale_type" AS sale_type,
            {acres} AS acres,
            p."land_use_description" AS land_use,
            (s."sale_price_num"::numeric / NULLIF({assessed}, 0)) AS sale_to_assessment_ratio
        FROM "sales" s
        JOIN "assessor_rollup" p ON p."parcel_number" = s."parcel_number"
        WHERE {assessed} > 0
          AND s."sale_price_num"::numeric > 0
          AND s."sale_date_iso" >= '2024-01-01'
          AND s."sale_type" = 'VALID SALE'
          AND {acres} >= 0.05
          AND lower(coalesce(p."land_use_description", '')) NOT LIKE '%water%'
          AND lower(coalesce(p."land_use_description", '')) NOT LIKE '%right%'
          AND lower(coalesce(p."land_use_description", '')) NOT LIKE '%common%'
        ORDER BY abs((s."sale_price_num"::numeric / NULLIF({assessed}, 0)) - 1) DESC
        LIMIT {int(limit)}
    """
    return "\n".join(line.rstrip() for line in sql.strip().splitlines())


def build_probe_sql(probe: str, columns: dict[str, set[str]], limit: int) -> str:
    if probe == PROBE_VALUE_PER_ACRE_OUTLIERS:
        return build_value_per_acre_sql(columns, limit)
    if probe == PROBE_LAND_IMPROVEMENT_IMBALANCE:
        return build_land_improvement_imbalance_sql(columns, limit)
    if probe == PROBE_ZONING_LAND_USE_MISMATCH:
        return build_zoning_land_use_mismatch_sql(columns, limit)
    if probe == PROBE_SALE_ASSESSMENT_GAP:
        return build_sale_assessment_gap_sql(columns, limit)
    raise CommandError(f"Probe {probe!r} is in the catalog but does not have v1 SQL yet.")


def rows_for_sql(sql: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def artifact_flags_for_row(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    acres = row.get("acres")
    try:
        acres_value = float(acres) if acres is not None else None
    except (TypeError, ValueError):
        acres_value = None
    if acres_value is None:
        flags.append("missing_acres")
    elif acres_value <= 0:
        flags.append("zero_acres")
    elif acres_value < 0.05:
        flags.append("tiny_parcel")

    land_use = str(row.get("land_use") or "").lower()
    for pattern in ARTIFACT_LAND_USE_PATTERNS:
        if pattern in land_use:
            flags.append(f"artifact_land_use:{pattern}")
    return flags


def annotate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in records:
        copy = dict(row)
        copy["artifact_flags"] = artifact_flags_for_row(row)
        annotated.append(copy)
    return annotated


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"row_count": len(records)}
    artifact_rows = [row for row in records if row.get("artifact_flags")]
    if artifact_rows:
        summary["artifact_row_count"] = len(artifact_rows)
        counts: dict[str, int] = {}
        for row in artifact_rows:
            for flag in row.get("artifact_flags", []):
                counts[flag] = counts.get(flag, 0) + 1
        summary["artifact_flags"] = counts
    land_uses = sorted({str(row.get("land_use")) for row in records if row.get("land_use")})
    if land_uses:
        summary["distinct_land_use_count"] = len(land_uses)
        summary["top_land_use_examples"] = land_uses[:12]
    numeric_fields = [
        "assessed_value",
        "land_value",
        "improvement_value",
        "acres",
        "value_per_acre",
        "land_to_improvement_ratio",
        "sale_price",
        "sale_to_assessment_ratio",
    ]
    for field in numeric_fields:
        values = [
            float(row[field])
            for row in records
            if row.get(field) is not None
        ]
        if not values:
            continue
        summary[field] = {
            "min": min(values),
            "median": percentile(values, 0.5),
            "p95": percentile(values, 0.95),
            "max": max(values),
        }
    return summary


def build_qa_flags(records: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    artifact_rows = [row for row in records if row.get("artifact_flags")]
    if artifact_rows:
        flags.append(f"{len(artifact_rows)} of {len(records)} rows have artifact flags.")
        artifact_counts: dict[str, int] = {}
        for row in artifact_rows:
            for flag in row.get("artifact_flags", []):
                artifact_counts[flag] = artifact_counts.get(flag, 0) + 1
        flags.extend(f"{count} row(s) flagged {flag}." for flag, count in sorted(artifact_counts.items()))
    if len(records) < 10:
        flags.append("Small result set; any finding should be treated as a weak lead.")
    return flags


def parse_model_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        object_start = cleaned.find("{")
        object_end = cleaned.rfind("}")
        if object_start != -1 and object_end != -1 and object_end > object_start:
            return json.loads(cleaned[object_start : object_end + 1])
        array_start = cleaned.find("[")
        array_end = cleaned.rfind("]")
        if array_start != -1 and array_end != -1 and array_end > array_start:
            return json.loads(cleaned[array_start : array_end + 1])
        raise


def build_editor_prompt(probe_meta: dict[str, Any], records: list[dict[str, Any]]) -> str:
    summary = summarize_records(records)
    qa_flags = build_qa_flags(records)
    caveats = [
        "Treat very small acreage ratios as outlier leads that need verification, not standalone conclusions.",
        "Do not publish a claim from a single parcel unless the idea is framed as a question to investigate.",
        "Use parcel examples as evidence, but prefer patterns across multiple rows.",
        "Rows with artifact_flags may support only rejected_ideas or explicit data-quality ideas; they cannot support publishable civic findings.",
    ]
    return f"""
You are the OpenSkagit Interpretation Editor.

Review this real civic data probe result.

Find the strongest public-facing ideas for "The Current."

Probe metadata:
{json.dumps(probe_meta, indent=2)}

Computed summary:
{json.dumps(json_ready(summary), indent=2)}

QA flags:
{json.dumps(qa_flags, indent=2)}

Editorial caveats:
{json.dumps(caveats, indent=2)}

Rules:
- No accusations.
- No speculation about motive.
- Use only the provided rows.
- Prefer patterns, outliers, mismatches, concentrations, civic tradeoffs, public cost, land use, tax productivity, and local meaning.
- Reject trivia.
- Do not turn extreme per-acre math into a publishable conclusion unless the acreage context supports it.
- The publish_score must reflect civic relevance, surprise, evidence strength, and plain-English clarity.
- Return only ideas with publish_score >= 75 in "ideas"; put weaker or risky concepts in "rejected_ideas".

Return JSON only:
{{
  "ideas": [
    {{
      "question": "...",
      "short_answer": "...",
      "why_it_matters": "...",
      "confidence": 0-100,
      "publish_score": 0-100,
      "data_used": "...",
      "caveats": ["..."],
      "what_to_check_next": "..."
    }}
  ],
  "rejected_ideas": [
    {{
      "question": "...",
      "reason": "..."
    }}
  ]
}}

Rows:
{json.dumps(json_ready(records), default=str)}
""".strip()


class Command(BaseCommand):
    help = "Run a local v1 discovery-agent test that drafts The Current ideas from PostGIS probe rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--probe",
            default=PROBE_VALUE_PER_ACRE_OUTLIERS,
            help=f"Probe to run. Implemented in this v1 test: {', '.join(sorted(SUPPORTED_PROBES))}.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Number of probe rows to send to the model. Default: 100.",
        )
        parser.add_argument(
            "--model",
            default="gpt-4.1-mini",
            help="OpenAI model for The Current draft ideas. Default: gpt-4.1-mini.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output only.",
        )
        parser.add_argument(
            "--dry-run-sql",
            action="store_true",
            help="Print the probe SQL and exit without calling OpenAI.",
        )

    def handle(self, *args, **options):
        probe_catalog = load_probe_catalog()
        probe = str(options["probe"]).strip()
        if probe not in probe_catalog:
            raise CommandError(
                f"Unknown probe {probe!r}. Add it to {PROBE_CATALOG_PATH} or choose an existing catalog probe."
            )
        if probe not in SUPPORTED_PROBES:
            raise CommandError(
                f"Probe {probe!r} is in the catalog but does not have v1 SQL yet. "
                f"Implemented probes: {', '.join(sorted(SUPPORTED_PROBES))}"
            )

        limit = int(options["limit"])
        if limit <= 0:
            raise CommandError("--limit must be greater than 0.")

        columns = fetch_columns()
        missing = summarize_missing_columns(columns)
        if missing:
            raise CommandError("Missing required PostGIS table/column(s): " + ", ".join(missing))

        sql = build_probe_sql(probe, columns, limit)
        if options["dry_run_sql"]:
            self.stdout.write(sql)
            return

        records = rows_for_sql(sql)
        if not records:
            raise CommandError("Probe returned no rows; check source data coverage and filters.")
        records = annotate_records(records)

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            api_key = getpass("OpenAI API key: ").strip()
            if not api_key:
                raise CommandError("OPENAI_API_KEY is required.")
            os.environ["OPENAI_API_KEY"] = api_key

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise CommandError("The openai package is not installed. Run: pip install -r requirements.txt") from exc

        model = str(options["model"]).strip()
        client = OpenAI()
        response = client.responses.create(
            model=model,
            input=build_editor_prompt(probe_catalog[probe], records),
            temperature=0.2,
        )
        output_text = response.output_text
        try:
            ideas = parse_model_json(output_text)
        except json.JSONDecodeError:
            if options["json"]:
                raise CommandError("Model did not return valid JSON.")
            self.stdout.write(output_text)
            raise CommandError("Model did not return valid JSON.")

        payload = {
            "probe": probe,
            "model": model,
            "row_count": len(records),
        }
        if isinstance(ideas, dict):
            payload.update(ideas)
        else:
            payload["ideas"] = ideas

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, default=str))
            return

        self.stdout.write(self.style.SUCCESS(f"Probe {probe} returned {len(records)} rows."))
        self.stdout.write(json.dumps(ideas, indent=2, default=str))
