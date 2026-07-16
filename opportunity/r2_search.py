from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

from .services import (
    ASSESSOR_DETAIL_URL,
    acres,
    current_use_zoning_flags,
    is_natural_resource_zone,
    is_public_or_civic_land_use,
    is_public_or_open_space_zone,
    is_resource_land_use,
    land_use_code,
    money,
    risk_flags,
    utility_labels,
)


DEFAULT_BUCKET = "openskagit"
DEFAULT_RESULT_LIMIT = 200
SAMPLE_VALUE_LIMIT = 50
PARCEL_SEARCH_KEY = "derived/parcel_search.parquet"

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze|"
    r"attach|detach|call|do|execute|install|load|secret|pragma|set|export|import)\b",
    re.IGNORECASE,
)
READ_PARQUET_RE = re.compile(r"read_parquet\s*\(\s*(['\"])(.*?)\1\s*\)", re.IGNORECASE)
READ_PARQUET_ALIAS_RE = re.compile(
    r"read_parquet\s*\(\s*(['\"])(.*?)\1\s*\)\s+(?:as\s+)?([a-z_][a-z0-9_]*)\b",
    re.IGNORECASE,
)
ALIAS_COLUMN_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\.\s*(?:\"([^\"]+)\"|([a-z_][a-z0-9_]*))", re.IGNORECASE)
SQL_ALIAS_KEYWORDS = {
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
    "on",
    "group",
    "order",
    "limit",
    "union",
    "select",
}
URL_OR_PATH_LITERAL_RE = re.compile(r"(['\"])((?:r2://|https?://|file:|/|\\\\|\.\.?/)[^'\"]+)\1", re.IGNORECASE)
BARE_LAND_USE_CODE_RE = re.compile(
    r"(?is)(?:trim\s*\(\s*)?(?:[a-z_][a-z0-9_]*\.)?land_use(?![a-z0-9_])\s*\)?\s*"
    r"(?:=|<>|!=|in\s*\(|not\s+in\s*\()\s*'?\d{2,3}'?"
)
BROAD_CITY_LIMITS_OR_RE = re.compile(
    r"(?is)(?:[a-z_][a-z0-9_]*\.)?inside_city_limits\s*=\s*true\s+or\s+"
    r"(?:lower\s*\(\s*)?(?:[a-z_][a-z0-9_]*\.)?city_name"
)
UNSAFE_LAND_USE_CAST_RE = re.compile(r"(?is)\bcast\s*\(\s*regexp_extract\s*\([^)]*land_use")


class R2SearchError(ValueError):
    pass


@dataclass(frozen=True)
class ParquetTable:
    path: str
    columns: tuple[str, ...]

    @property
    def key(self) -> str:
        return self.path.split("/", 3)[-1]


@dataclass(frozen=True)
class R2GeneratedSearch:
    short_name: str
    title: str
    criteria_summary: str
    assumptions: list[str]
    sql: str
    params: list[Any]
    tool_trace: list[dict[str, Any]]


@dataclass(frozen=True)
class R2SearchResult:
    generated: R2GeneratedSearch
    raw_rows: list[dict[str, Any]]
    hydrated_rows: list[dict[str, Any]]
    diagnostics: dict[str, Any]


def configured_bucket() -> str:
    return os.environ.get("R2_BUCKET", DEFAULT_BUCKET).strip() or DEFAULT_BUCKET


def r2_path(key: str) -> str:
    return f"r2://{configured_bucket()}/{key.lstrip('/')}"


def parcel_search_path() -> str:
    return r2_path(PARCEL_SEARCH_KEY)


@lru_cache(maxsize=1)
def schema_reference_text() -> str:
    return _read_project_data_file("schema_dump.md")


@lru_cache(maxsize=1)
def code_reference_text() -> str:
    return _read_project_data_file("appraisal_code_reference.md")


@lru_cache(maxsize=1)
def ontology_reference_text() -> str:
    return _read_project_data_file("opportunity_search_ontology.md")


@lru_cache(maxsize=1)
def zoning_mcp_reference_text() -> str:
    base = _read_project_data_file("opportunity_zoning_reference.md")
    try:
        from django.db.models import Count

        from zoning_mcp.models import Jurisdiction, Zone, ZoningCodeSection, ZoningSourceTable, ZoningUseRule
    except Exception:
        return base

    try:
        jurisdictions = list(Jurisdiction.objects.order_by("key"))
        lines = [
            base,
            "",
            "## Live zoning_mcp Corpus Summary",
            "",
            "This section is loaded from the zoning_mcp database used by the zoning advisory tools.",
            "Use it as source-code/legal context. Parcel fields remain screening signals and must be paired with parcel facts.",
            "",
            (
                f"Corpus counts: {len(jurisdictions)} jurisdictions, "
                f"{Zone.objects.count()} zones, {ZoningUseRule.objects.count()} structured use rules, "
                f"{ZoningCodeSection.objects.count()} code sections, {ZoningSourceTable.objects.count()} source tables."
            ),
            "",
        ]
        for jurisdiction in jurisdictions:
            zones = list(Zone.objects.filter(jurisdiction=jurisdiction).order_by("zone_code"))
            status_rows = (
                ZoningUseRule.objects.filter(jurisdiction=jurisdiction)
                .values("normalized_status")
                .annotate(n=Count("id"))
                .order_by("normalized_status")
            )
            possible_uses = (
                ZoningUseRule.objects.filter(
                    jurisdiction=jurisdiction,
                    normalized_status__in=["P", "AC", "AD", "HE", "C", "CUP"],
                )
                .values("normalized_use_key", "use_name")
                .annotate(n=Count("id"))
                .order_by("-n", "normalized_use_key")[:18]
            )
            chapters = (
                ZoningCodeSection.objects.filter(jurisdiction=jurisdiction)
                .values("chapter_ref", "chapter_title")
                .annotate(n=Count("id"))
                .order_by("chapter_ref")[:18]
            )
            source_tables = (
                ZoningSourceTable.objects.filter(jurisdiction=jurisdiction)
                .values("chapter_ref", "caption", "nearest_heading")
                .annotate(n=Count("id"))
                .order_by("chapter_ref", "caption")[:12]
            )
            zone_text = ", ".join(
                f"{zone.zone_code}" + (f"={zone.zone_name}" if zone.zone_name else "") for zone in zones
            )
            status_text = ", ".join(f"{row['normalized_status']}:{row['n']}" for row in status_rows) or "none"
            use_text = "; ".join(
                f"{row['normalized_use_key']} ({row['use_name']}) [{row['n']} zones/status rows]"
                for row in possible_uses
            ) or "No structured possible-use rows."
            chapter_text = "; ".join(
                f"{row['chapter_ref']} {row['chapter_title']} [{row['n']}]"
                for row in chapters
            ) or "No imported sections."
            table_text = "; ".join(
                f"{row['chapter_ref']} {row['caption'] or row['nearest_heading']}"
                for row in source_tables
            ) or "No imported source tables."
            lines.extend(
                [
                    f"### {jurisdiction.display_name} (`{jurisdiction.key}`)",
                    f"- Source: {jurisdiction.zoning_title}; {jurisdiction.code_source}; {jurisdiction.source_url}",
                    f"- Coverage: {jurisdiction.extraction_status}",
                    f"- Zones: {zone_text}",
                    f"- Structured rule statuses: {status_text}",
                    f"- Common allowed/possible use keys: {use_text}",
                    f"- Imported code chapters: {chapter_text}",
                    f"- Imported source tables: {table_text}",
                    "",
                ]
            )
        lines.extend(
            [
                "## SQL Guidance From zoning_mcp",
                "",
                "- Do not infer legal use permission only from `derived/parcel_search.parquet.zoning_code_short`.",
                "- For city prompts, match the place with parcel facts and use zoning_mcp zone families for compatibility evidence.",
                "- Sedro-Woolley source residential zones are R_1, R_5, R_7, and R_15; parcel_search may represent incorporated parcels as `CITY` and nearby county residential context as RI, RRv/RRV, or RVR.",
                "- Mount Vernon residential/mobile zones include R_A, R_1, R_2, R_3, R_4, R_O, and MHP; commercial/industrial zones include C_1/C_2/C_3/C_4/C_L, LC, M_1, M_2, and P_O.",
                "- Burlington residential/mixed residential zones include RD, RA_1, RA_2, MUR_1, and MUR_2; commercial/industrial zones include MUC_1, MUC_2, CI_1, and CI_2.",
                "- Anacortes residential zones include R1, R2, R2A, R3, R3A, R4, and R4A; commercial/mixed/industrial zones include C, CBD, CM, CM2, LM, LM1, MMU, MS, HM, and I.",
                "- Skagit County rural residential-compatible zones include RI, RRV/RRv, and RVR; resource zones such as AG_NRL, IF_NRL, SF_NRL, and RRC_NRL may contain residences but are not residential zoning unless the prompt allows rural/resource context.",
            ]
        )
        return "\n".join(lines)
    except Exception:
        return base


@lru_cache(maxsize=1)
def parquet_registry() -> dict[str, ParquetTable]:
    text = schema_reference_text()
    registry: dict[str, ParquetTable] = {}
    heading_re = re.compile(r"^##\s+(r2://[^\s]+)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    for index, match in enumerate(matches):
        path = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        columns = tuple(_parse_markdown_columns(text[start:end]))
        if not columns:
            continue
        table = ParquetTable(path=path, columns=columns)
        registry[path] = table
        configured = _with_configured_bucket(path)
        registry[configured] = ParquetTable(path=configured, columns=columns)
    return registry


def validate_r2_search_sql(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> str:
    stripped = (sql or "").strip()
    if not stripped:
        raise R2SearchError("The generated SQL was empty.")
    if ";" in stripped:
        raise R2SearchError("Only one SQL statement is allowed, and semicolons are not allowed.")
    if not re.match(r"(?is)^(select|with)\b", stripped):
        raise R2SearchError("Only read-only SELECT/WITH DuckDB queries are allowed.")
    if re.match(r"(?is)^with\b", stripped) and re.search(r"(?is)\)\s*$", stripped) and not re.search(r"(?is)\)\s*select\b", stripped):
        raise R2SearchError("WITH queries must include a final SELECT after the CTE definitions.")
    if FORBIDDEN_SQL.search(stripped):
        raise R2SearchError("The generated SQL used a forbidden operation.")
    if not re.search(r"(?i)\bparcel_number\b", stripped):
        raise R2SearchError("The query must return a normalized parcel_number column.")
    if params:
        raise R2SearchError("DuckDB/R2 opportunity search does not accept SQL params; inline constants in generated SQL.")
    if re.search(r"(?<!%)%s(?![A-Za-z0-9_])|\?", stripped):
        raise R2SearchError("DuckDB/R2 opportunity search does not accept SQL placeholders; inline constants in generated SQL.")
    if BARE_LAND_USE_CODE_RE.search(stripped):
        raise R2SearchError(
            "derived parcel_search.land_use stores full labels like '(911) UNDEVELOPED LAND', not bare numeric codes. "
            "Extract a code with regexp_extract(COALESCE(land_use, ''), '^\\\\((\\\\d+)\\\\)', 1) before code comparisons."
        )
    if BROAD_CITY_LIMITS_OR_RE.search(stripped):
        raise R2SearchError(
            "Do not use inside_city_limits = TRUE as a standalone OR branch for a named place search; "
            "that matches every incorporated city. Pair city limits with the named city, and use situs_city_state_zip/postal city for nearby unincorporated vicinity."
        )
    if UNSAFE_LAND_USE_CAST_RE.search(stripped):
        raise R2SearchError(
            "Do not CAST(regexp_extract(...land_use...)) directly; blank land_use values produce empty strings. "
            "Use TRY_CAST(NULLIF(regexp_extract(COALESCE(land_use, ''), '^\\\\((\\\\d+)\\\\)', 1), '') AS INTEGER) "
            "or compare the extracted code as text."
        )

    registry = parquet_registry()
    parquet_refs = READ_PARQUET_RE.findall(stripped)
    if not parquet_refs:
        raise R2SearchError("The query must read from allowed R2 parquet files with read_parquet().")
    for _, path in parquet_refs:
        if path not in registry:
            raise R2SearchError(f"R2 parquet path is not allowed for opportunity search: {path}")
    for _, value in URL_OR_PATH_LITERAL_RE.findall(stripped):
        if value not in registry:
            raise R2SearchError(f"Arbitrary paths and URLs are not allowed in generated SQL: {value}")
    _validate_alias_columns(stripped, registry)
    return stripped


def parse_generated_r2_search_response(text: str) -> R2GeneratedSearch:
    payload = _parse_json_object(text)
    required = {"title", "criteria_summary", "sql"}
    missing = sorted(required - set(payload))
    if missing:
        raise R2SearchError(f"The AI response was missing: {', '.join(missing)}.")
    assumptions = _coerce_assumptions(payload.get("assumptions"))
    params = _coerce_params(payload.get("params"))
    return R2GeneratedSearch(
        short_name=str(payload.get("short_name") or payload.get("title") or "Opportunity")[:80],
        title=str(payload.get("title") or "AI opportunity search")[:220],
        criteria_summary=str(payload.get("criteria_summary") or "")[:1600],
        assumptions=assumptions,
        sql=str(payload.get("sql") or ""),
        params=params,
        tool_trace=[],
    )


class DuckDBR2OpportunityClient:
    def __init__(self, con: Any | None = None) -> None:
        self.bucket = configured_bucket()
        self.account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
        self.access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        self.secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        self.con = con
        self._connected = con is not None

    def connect(self):
        if self.con is None:
            import duckdb

            self.con = duckdb.connect(database=":memory:")
        if self._connected:
            return self.con
        self._require_credentials()
        self.con.execute("INSTALL httpfs")
        self.con.execute("LOAD httpfs")
        self.con.execute(
            f"""
            CREATE OR REPLACE SECRET openskagit_r2 (
                TYPE R2,
                KEY_ID '{_sql_string(self.access_key_id)}',
                SECRET '{_sql_string(self.secret_access_key)}',
                ACCOUNT_ID '{_sql_string(self.account_id)}'
            )
            """
        )
        self._connected = True
        return self.con

    def sample_values(self, parquet_path: str, column: str, limit: int = 30) -> str:
        table = _require_table(parquet_path)
        if column not in table.columns:
            raise R2SearchError(f"Column {column} is not listed for {parquet_path}.")
        limit = max(1, min(int(limit or 30), SAMPLE_VALUE_LIMIT))
        identifier = _quote_identifier(column)
        sql = (
            f"SELECT {identifier} AS val, COUNT(*) AS n "
            f"FROM read_parquet('{_sql_string(parquet_path)}') "
            f"GROUP BY {identifier} ORDER BY n DESC LIMIT {limit}"
        )
        try:
            cursor = self.connect().execute(sql)
        except R2SearchError:
            raise
        except Exception as exc:
            raise R2SearchError(f"DuckDB sample_values query failed: {_duckdb_error_message(exc)}") from exc
        columns = [desc[0] for desc in cursor.description or []]
        rows = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
        return "\n".join(json.dumps(_json_safe(row), default=str) for row in rows) or "(no values)"

    def execute(self, sql: str, limit: int = DEFAULT_RESULT_LIMIT) -> list[dict[str, Any]]:
        stripped = validate_r2_search_sql(sql)
        wrapped = f"SELECT * FROM ({stripped}) opportunity_ai_search LIMIT {int(limit)}"
        try:
            cursor = self.connect().execute(wrapped)
        except R2SearchError:
            raise
        except Exception as exc:
            raise R2SearchError(f"DuckDB execution failed: {_duckdb_error_message(exc)}") from exc
        columns = [desc[0] for desc in cursor.description or []]
        if "parcel_number" not in columns:
            raise R2SearchError("The query result did not include parcel_number.")
        return [_json_safe(dict(zip(columns, row, strict=False))) for row in cursor.fetchall()]

    def hydrate_rows(self, raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raw_by_parcel: dict[str, dict[str, Any]] = {}
        parcel_numbers: list[str] = []
        for row in raw_rows:
            parcel_number = str(row.get("parcel_number") or "").strip().upper()
            if not parcel_number or parcel_number in raw_by_parcel:
                continue
            raw_by_parcel[parcel_number] = row
            parcel_numbers.append(parcel_number)
        if not parcel_numbers:
            return []

        base_by_parcel = self._fetch_parcel_search_rows(parcel_numbers)
        hydrated = []
        for parcel_number in parcel_numbers:
            raw = raw_by_parcel[parcel_number]
            base = base_by_parcel.get(parcel_number, {})
            hydrated.append(format_r2_result_row(parcel_number, base, raw))
        return hydrated

    def _fetch_parcel_search_rows(self, parcel_numbers: list[str]) -> dict[str, dict[str, Any]]:
        if not parcel_numbers:
            return {}
        values = ", ".join(f"'{_sql_string(parcel)}'" for parcel in parcel_numbers)
        sql = (
            f"SELECT * FROM read_parquet('{_sql_string(parcel_search_path())}') "
            f"WHERE upper(trim(parcel_number)) IN ({values})"
        )
        try:
            cursor = self.connect().execute(sql)
        except R2SearchError:
            raise
        except Exception as exc:
            raise R2SearchError(f"DuckDB result hydration failed: {_duckdb_error_message(exc)}") from exc
        columns = [desc[0] for desc in cursor.description or []]
        rows = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
        return {str(row.get("parcel_number") or "").strip().upper(): _json_safe(row) for row in rows}

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "R2_ACCOUNT_ID": self.account_id,
                "R2_ACCESS_KEY_ID": self.access_key_id,
                "R2_SECRET_ACCESS_KEY": self.secret_access_key,
            }.items()
            if not value
        ]
        if missing:
            raise R2SearchError(f"Missing required R2 environment variables: {', '.join(missing)}")


def generate_r2_search(
    prompt: str,
    *,
    model: str,
    error_feedback: str = "",
    extra_context: str = "",
    client: Any | None = None,
    r2_client: DuckDBR2OpportunityClient | None = None,
    max_tool_turns: int = 6,
) -> R2GeneratedSearch:
    client = client or _openai_client()
    r2_client = r2_client or DuckDBR2OpportunityClient()
    tool_trace: list[dict[str, Any]] = []
    response = None
    tool_outputs: list[dict[str, Any]] | str = _initial_user_prompt(prompt, error_feedback)
    previous_response_id = None
    for _ in range(max_tool_turns):
        kwargs = {
            "model": model,
            "instructions": _generation_instructions(extra_context),
            "input": tool_outputs,
            "tools": [_sample_values_tool_schema()],
            "temperature": 0.1,
            "max_output_tokens": 2200,
        }
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id
        response = client.responses.create(**kwargs)
        calls = _response_function_calls(response)
        if not calls:
            generated = parse_generated_r2_search_response(_response_text(response))
            validate_r2_search_sql(generated.sql, generated.params)
            return R2GeneratedSearch(
                short_name=generated.short_name,
                title=generated.title,
                criteria_summary=generated.criteria_summary,
                assumptions=generated.assumptions,
                sql=generated.sql,
                params=generated.params,
                tool_trace=tool_trace,
            )

        previous_response_id = getattr(response, "id", None)
        next_outputs = []
        for call in calls:
            output = _dispatch_tool_call(call, r2_client)
            tool_trace.append(
                {
                    "tool": call["name"],
                    "arguments": call["arguments"],
                    "output_preview": output[:500],
                }
            )
            next_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": output[:4000],
                }
            )
        tool_outputs = next_outputs
    raise R2SearchError("The AI used too many schema/value tool turns without producing SQL.")


def run_generated_r2_search(
    generated: R2GeneratedSearch,
    *,
    r2_client: DuckDBR2OpportunityClient | None = None,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    r2_client = r2_client or DuckDBR2OpportunityClient()
    raw_rows = r2_client.execute(generated.sql, limit=limit)
    hydrated_rows = r2_client.hydrate_rows(raw_rows)
    diagnostics = {
        "source": "duckdb_r2",
        "raw_row_count": len(raw_rows),
        "hydrated_row_count": len(hydrated_rows),
        "parquet_paths": sorted({path for _, path in READ_PARQUET_RE.findall(generated.sql)}),
        "tool_trace": generated.tool_trace,
        "registry_table_count": len(parquet_registry()),
    }
    return raw_rows, hydrated_rows, diagnostics


def format_r2_result_row(parcel_number: str, base: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    row = {**base, **{key: value for key, value in raw.items() if value not in (None, "")}}
    address = str(row.get("situs_address") or row.get("address") or "").strip()
    city = _city_label(row.get("city_name") or row.get("situs_city_state_zip") or "")
    land_use = str(row.get("land_use") or "")
    code = land_use_code(land_use)
    lat, lng = _valid_lat_lng(row.get("gis_y"), row.get("gis_x"))
    assessed = row.get("assessed_value")
    building = row.get("assessor_building_value", row.get("building_value"))
    land_value = row.get("improved_land_value")
    if land_value in (None, ""):
        land_value = _derived_land_value(assessed, building)
    zone_id = row.get("zoning_code_short") or row.get("zoning_code") or ""
    zone_name = row.get("zoning_label") or ""
    reasons = _reason_labels(raw.get("match_reasons") or row.get("match_reasons"))
    feature_bits = []
    primary_living_area = _coerce_number(row.get("primary_building_living_area"))
    total_garage_area = _coerce_number(row.get("total_garage_area"))
    if primary_living_area:
        feature_bits.append(f"{primary_living_area:,.0f} sf primary building")
    if row.get("primary_actual_year_built"):
        feature_bits.append(f"built {row['primary_actual_year_built']}")
    if row.get("years_since_last_valid_sale") is not None:
        feature_bits.append(f"{row['years_since_last_valid_sale']} years since valid sale")
    if total_garage_area:
        feature_bits.append(f"{total_garage_area:,.0f} sf garage area")

    map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}" if lat is not None and lng is not None else ""
    map_embed_url = f"https://maps.google.com/maps?q={lat},{lng}&z=17&output=embed" if lat is not None and lng is not None else ""
    display_row = {
        "parcel_number": parcel_number,
        "parcel_url": ASSESSOR_DETAIL_URL.format(parcel_number=parcel_number),
        "location": _location_label(address, city),
        "city": city,
        "owner": row.get("owner_name") or "",
        "acres": row.get("acres"),
        "acres_fmt": acres(row.get("acres")),
        "land_use": land_use,
        "land_use_code": code,
        "current_use": _land_use_label(land_use),
        "utilities": row.get("utilities") or "",
        "feature_labels": feature_bits,
        "signal_labels": reasons[:4] or feature_bits[:4],
        "past_due_years": [],
        "effective_frontage": row.get("effective_frontage"),
        "actual_frontage": row.get("actual_frontage"),
        "zoning": zone_id or zone_name or "Unknown zoning",
        "zone_name": zone_name,
        "waza_general": row.get("waza_general") or row.get("comp_plan_lud") or "",
        "zone_definition": _zone_definition(zone_id, zone_name, row),
        "zone_url": row.get("reference_url") or "",
        "assessed_value": assessed,
        "building_value": building,
        "land_value": land_value,
        "assessed_value_fmt": money(assessed),
        "land_value_fmt": money(land_value),
        "building_value_fmt": money(building),
        "score": int(_coerce_number(row.get("score")) or 0),
        "risk_flags": [],
        "current_use_zoning_audit": {},
        "lat": lat,
        "lng": lng,
        "map_url": map_url,
        "map_embed_url": map_embed_url,
        "aerial_image_url": "",
        "aerial_image_source": "",
        "auditor_url": "",
        "auditor_label": "",
        "auditor_note": "",
        "recent_document_url": "",
        "source_tab": "ai-search",
        "source_tab_label": "Opportunity",
        "ai_match_reasons": reasons,
        "why_it_ranks": "; ".join(reasons[:3]) if reasons else "Matched the natural-language search.",
        "parcel_data": row,
    }
    display_row["risk_flags"] = risk_flags(
        "No parcel geometry" if not display_row["map_url"] else None,
        "Unknown zoning" if not zone_id and not zone_name else None,
        "Natural resource zoning" if is_natural_resource_zone(zone_id, zone_name, display_row["waza_general"]) else None,
        "Public/open-space zoning" if is_public_or_open_space_zone(display_row["waza_general"]) else None,
        "Public/civic or moorage use" if is_public_or_civic_land_use(land_use) else None,
        "Resource land" if is_resource_land_use(land_use) else None,
        "No utility signal" if "utilities" in row and not utility_labels(row.get("utilities")) else None,
    ) + current_use_zoning_flags(display_row)
    return display_row


def _parse_markdown_columns(section: str) -> list[str]:
    columns: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|:") or "column_name" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0] and set(cells[0]) != {"-"}:
            columns.append(cells[0])
    return columns


def _with_configured_bucket(path: str) -> str:
    match = re.match(r"^r2://([^/]+)/(.*)$", path)
    if not match:
        return path
    return f"r2://{configured_bucket()}/{match.group(2)}"


def _require_table(path: str) -> ParquetTable:
    registry = parquet_registry()
    if path not in registry:
        raise R2SearchError(f"R2 parquet path is not allowed for opportunity search: {path}")
    return registry[path]


def _validate_alias_columns(sql: str, registry: dict[str, ParquetTable]) -> None:
    aliases: dict[str, ParquetTable] = {}
    for _, path, alias in READ_PARQUET_ALIAS_RE.findall(sql):
        alias_key = alias.lower()
        if alias_key in SQL_ALIAS_KEYWORDS or path not in registry:
            continue
        aliases[alias_key] = registry[path]
    if not aliases:
        return

    for alias, quoted_column, bare_column in ALIAS_COLUMN_RE.findall(sql):
        table = aliases.get(alias.lower())
        if not table:
            continue
        column = quoted_column or bare_column
        if _column_exists(table, column):
            continue
        if table.key == PARCEL_SEARCH_KEY and column.lower() == "utilities":
            raise R2SearchError(
                "Column utilities is not listed for alias ps on derived/parcel_search.parquet. "
                "Utilities live in assessor.parquet as \"Utilities\"; join it as a on ps.parcel_number = TRIM(a.\"Parcel Number\"), "
                "select a.\"Utilities\" AS utilities, and filter TRIM(COALESCE(a.\"Utilities\", '')) <> ''."
            )
        if table.key == PARCEL_SEARCH_KEY and column.lower() in {"building_value", "year_built"}:
            raise R2SearchError(
                f"Column {column} is not listed for alias {alias} on derived/parcel_search.parquet. "
                "Do not select generic building_value or year_built from parcel_search. "
                "Use assessor_building_value, primary_building_improvement_value, total_improvement_value, "
                "primary_actual_year_built, oldest_actual_year_built, or primary_effective_year_built when those fields are needed."
            )
        raise R2SearchError(f"Column {column} is not listed for alias {alias} on {table.path}.")


def _column_exists(table: ParquetTable, column: str) -> bool:
    wanted = column.lower()
    return any(existing.lower() == wanted for existing in table.columns)


def _read_project_data_file(name: str) -> str:
    path = Path(settings.BASE_DIR) / "data" / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _sql_string(value: str) -> str:
    return str(value).replace("'", "''")


def _duckdb_error_message(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0][:600] or type(exc).__name__


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _sample_values_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "sample_values",
        "description": "Get distinct values and counts for a listed column in an allowed R2 parquet file. Use only for value-level checks after reading the schema.",
        "parameters": {
            "type": "object",
            "properties": {
                "parquet_path": {"type": "string"},
                "column": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["parquet_path", "column"],
            "additionalProperties": False,
        },
    }


def _dispatch_tool_call(call: dict[str, Any], r2_client: DuckDBR2OpportunityClient) -> str:
    if call["name"] != "sample_values":
        return f"ERROR: Unknown tool {call['name']}"
    arguments = call.get("arguments") or {}
    if isinstance(arguments, dict):
        args = arguments
    else:
        try:
            args = json.loads(str(arguments or "{}"))
        except json.JSONDecodeError as exc:
            return f"ERROR: invalid JSON arguments: {exc}"
    try:
        return r2_client.sample_values(args.get("parquet_path") or "", args.get("column") or "", args.get("limit") or 30)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def _response_function_calls(response: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in getattr(response, "output", []) or []:
        item_type = _response_item_value(item, "type")
        if item_type != "function_call":
            continue
        name = _response_item_value(item, "name")
        arguments = _response_item_value(item, "arguments", "{}")
        call_id = _response_item_value(item, "call_id") or _response_item_value(item, "id")
        calls.append({"name": name, "arguments": arguments, "call_id": call_id})
    return calls


def _response_item_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text)
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else None) or []
        for block in content:
            value = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else None)
            if value:
                chunks.append(str(value))
    return "\n".join(chunks) or str(response)


def _openai_client():
    from openai import OpenAI

    timeout = float(os.environ.get("OPPORTUNITY_SEARCH_TIMEOUT", "75"))
    return OpenAI(timeout=timeout)


def _initial_user_prompt(prompt: str, error_feedback: str = "") -> str:
    feedback = f"\n\nPrevious query failed validation or execution:\n{error_feedback}\n\nFix it." if error_feedback else ""
    return f"User opportunity search prompt:\n{prompt}{feedback}"


def _generation_instructions(extra_context: str = "") -> str:
    return f"""
You write DuckDB SQL over parquet files in R2 for OpenSkagit Parcel Book opportunity search.
Return only one compact JSON object with keys: short_name, title, criteria_summary, assumptions, sql, params.
params must be [].
short_name must be 2-3 plain words with spaces for navigation, like Tax Pressure, Teardown Leads, or Small Lot Splits. Never return a concatenated slug or camelCase short_name.

Critical DuckDB/R2 rules:
- Use only read_parquet() paths listed in the schema below.
- SQL must be one SELECT or WITH statement. No semicolons. No mutations, temp objects, INSTALL, LOAD, SECRET, ATTACH, PRAGMA, COPY, EXPORT, SET, or admin statements.
- WITH queries must include the final SELECT that returns rows. Do not stop after defining a CTE.
- Always return a normalized parcel_number column.
- Prefer derived/parcel_search.parquet for parcel-level opportunity screens. Join raw files only when the requested signal needs detail rows.
- Keep SELECT lists minimal and schema-grounded. It is valid to return only ps.parcel_number plus required evidence columns such as land_use, acres, assessed_value, years_since_last_valid_sale, utilities, quality_codes, score, or match_reasons. Do not add convenience columns unless they are explicitly listed in the selected parquet schema.
- In derived/parcel_search.parquet, do not invent generic year_built or building_value columns. Use primary_actual_year_built, oldest_actual_year_built, primary_effective_year_built, assessor_building_value, primary_building_improvement_value, or total_improvement_value when those fields are listed in the selected parquet schema.
- When a query has more than one read_parquet() source, give each source an alias and qualify every selected, filtered, joined, and ordered column with that alias. For example, use ps.acres, ps.improvement_building_count, a."Utilities", and ps.parcel_number AS parcel_number. Avoid unqualified columns like acres, utilities, land_use, or improvement_building_count in joined queries.
- When combining OR land-use families with AND thresholds, parenthesize the OR group. Use `(commercial_range OR service_range) AND ps.assessed_value >= 1000000`, not `commercial_range OR service_range AND ps.assessed_value >= 1000000`.
- For resource production acreage prompts, parenthesize every resource-code OR branch before applying acreage: `(resource_code BETWEEN 810 AND 890 OR resource_code IN (920, 930, 940, 941)) AND ps.acres > 20`. Never write `resource_code BETWEEN 810 AND 890 OR resource_code IN (...) AND ps.acres > 20`.
- Utilities are not present in derived/parcel_search.parquet. For prompts requiring utilities, join r2://openskagit/assessor.parquet as a on ps.parcel_number = TRIM(a."Parcel Number"), select a."Utilities" AS utilities, and filter TRIM(COALESCE(a."Utilities", '')) <> ''. Do not use ps.utilities and do not compare utilities to 'Yes'; raw utilities are token strings such as power/water/septic/sewer codes.
- For prompts saying no improvements, no buildings, vacant, bare, or unimproved land, land_use labels alone are not enough. Filter COALESCE(ps.improvement_building_count, 0) = 0 and select ps.improvement_building_count for verification unless the prompt explicitly allows existing improvements.
- For no-utilities or no-exemptions prompts, join r2://openskagit/assessor.parquet and select TRIM(a."Utilities") AS utilities and/or TRIM(a."Exemptions") AS exemptions. derived/parcel_search.parquet does not contain exemptions.
- For named place searches, never use inside_city_limits = TRUE by itself as an OR branch; it matches all incorporated cities. Use city_name/situs_city_state_zip for the named place, for example lower(ps.city_name) = 'sedro-woolley' OR lower(ps.situs_city_state_zip) LIKE '%sedro-woolley%'. For "immediate unincorporated vicinity", postal city/situs_city_state_zip is often safer than inside_city_limits.
- "Skagit County" means the whole dataset/countywide search. Do not add city_name LIKE '%skagit%' or situs_city_state_zip LIKE '%skagit%' for countywide prompts; those fields contain parcel cities/addresses, not the county name.
- "Flood plain" is a condition/exclusion, not a city or place name. Do not filter city_name or situs_city_state_zip for 'flood'. If no floodplain field is listed in the allowed schema, state that limitation in assumptions/match_reasons rather than inventing a floodplain hard filter.
- For private bare/recreation land exclusions such as public, school, cemetery, church, moorage, or condo, apply exclusions to current `owner_name`, current `situs_address`, and current `land_use` evidence. Historical sale buyer/seller text alone should not drive current exclusions.
- In derived/parcel_search.parquet, land_use is a full assessor label like "(911) UNDEVELOPED LAND INCORPORATED", not a bare code. For code filters, create land_use_code with regexp_extract(COALESCE(land_use, ''), '^\\((\\d+)\\)', 1) and compare that derived code. Never write land_use IN ('911') or TRIM(land_use) = '181'. For numeric code ranges, never CAST the regexp_extract result directly because blanks become ''. Use TRY_CAST(NULLIF(regexp_extract(COALESCE(ps.land_use, ''), '^\\((\\d+)\\)', 1), '') AS INTEGER) BETWEEN 710 AND 790, or compare text prefixes/codes.
- Never return personal property, commercial, or industrial parcels in AI opportunity searches. Exclude land-use code 0, commercial/service codes 510-590 and 610-691, industrial/manufacturing codes 210-360, and labels containing PERSONAL PROPERTY, COMMERCIAL, or INDUSTRIAL.
- For SFR/single-family prompts, use DOR land_use codes 110, 111, 112, and 113 only. Manufactured/mobile home codes 180 and 185 are dwelling-like but are not SFR unless the prompt explicitly asks for mobile/manufactured homes.
- For two-to-four-unit, duplex, triplex, fourplex, or small multifamily prompts, use DOR land_use code 120 as the primary hard filter. Do not require improvement_building_count BETWEEN 2 AND 4 unless the prompt explicitly asks for a building count; improvement_building_count counts building records, not dwelling units. Do not require city source zoning codes such as RA_1/MUR_1 against parcel_search zoning fields; incorporated city parcels may appear as CITY.
- For quality dwelling prompts, quality/class codes are in r2://openskagit/improvements.parquet as imprv_det_class_cd. Join improvements as i on ps.parcel_number = TRIM(i.ParcelNumber) and filter the requested class exactly: MSL=low, MSF=fair, MSA=average. Do not satisfy an average-quality prompt by only excluding MSL. Do not search condition_codes for MSL/MSF/MSA; condition_codes/condition_cd are a separate condition family with values like L, F, A, G, VG, and E. Return the evidence too, such as string_agg(DISTINCT TRIM(i.imprv_det_class_cd), ' | ') AS quality_codes or 'MSA average improvement class' AS match_reasons.
- For built-before/older-building prompts, use and select primary_actual_year_built or oldest_actual_year_built when available. Do not alias assessor_year_built as year_built when the more specific improvement-summary year fields exist.
- Raw VARCHAR code/id columns in improvements.parquet, land.parquet, assessor.parquet, and sales.parquet may be fixed-width and padded. Use TRIM() for equality filters and joins on code/id columns.
- Parcel identifiers differ by file: "ParcelNumber" in improvements.parquet and land.parquet, "Parcel Number" in assessor.parquet and sales.parquet, parcel_number in derived/*.parquet.
- Quote mixed-case and space-containing column names, for example "Parcel Number" and "Eff Year Built".
- Land-use/DOR use codes live on parcel-level tables, not improvements.parquet.
- Optional useful output columns are score and match_reasons. match_reasons may be a DuckDB list or string with concise screening signals.
- When a WHERE/JOIN filter depends on a non-obvious assessor code, select that code or add it to match_reasons so the result evaluator and UI can explain why the row matched.
- Treat zoning, comp-plan, and opportunity labels as screening signals, not legal/permit determinations.
- For residential-zone prompts, do not use only `ps.zoning_code_short LIKE 'R%'`. Use the zoning_mcp reference below to combine source-code zone families with parcel_search signals: city incorporated parcels may show `CITY`, Skagit County residential context may show RI/RRv/RVR, and Sedro-Woolley city source zones are R_1/R_5/R_7/R_15.
- For Sedro-Woolley residential searches, include both incorporated city and immediate vicinity evidence when the prompt wording allows it: `(lower(ps.city_name) = 'sedro-woolley' OR lower(ps.situs_city_state_zip) LIKE '%sedro woolley%' OR lower(ps.situs_city_state_zip) LIKE '%sedro-woolley%')`, then require residential land-use/dwelling evidence plus residential-compatible zoning/context.
- If the exact stored value is uncertain, call sample_values for a listed column before final SQL.

Allowed R2 schema:
{schema_reference_text()}

Appraisal/code reference:
{code_reference_text()}

Opportunity search ontology:
{ontology_reference_text()}

Zoning MCP reference:
{zoning_mcp_reference_text()}

Additional app context:
{extra_context or "No extra context."}
""".strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise R2SearchError("The AI response was not valid JSON.")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise R2SearchError("The AI response must be a JSON object.")
    return parsed


def _coerce_assumptions(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                value = parsed
            else:
                value = [stripped]
        else:
            value = [stripped]
    elif isinstance(value, dict):
        value = [json.dumps(value, sort_keys=True)]
    elif not isinstance(value, list | tuple):
        value = [value]
    return [str(item)[:240] for item in value if str(item).strip()]


def _coerce_params(value: Any) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"", "null", "none", "{}"}:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            return parsed if isinstance(parsed, list) else [parsed]
        return [stripped]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _reason_labels(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return [str(item)[:120] for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item)[:120] for item in parsed if str(item).strip()]
        return [part.strip()[:120] for part in re.split(r"[;\n|]", stripped) if part.strip()]
    return [str(value)[:120]]


def _valid_lat_lng(lat_value: Any, lng_value: Any) -> tuple[float | None, float | None]:
    lat = _coerce_number(lat_value)
    lng = _coerce_number(lng_value)
    if lat is None or lng is None:
        return None, None
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None, None


def _coerce_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derived_land_value(assessed: Any, building: Any) -> Any:
    assessed_num = _coerce_number(assessed)
    building_num = _coerce_number(building)
    if assessed_num is None or building_num is None:
        return None
    return max(assessed_num - building_num, 0)


def _city_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    first = text.split(",", 1)[0].strip()
    first = re.sub(r"\s+WA(?:\s+\d{5}(?:-\d{4})?)?$", "", first, flags=re.IGNORECASE).strip()
    return first or text


def _location_label(address: str, city: str) -> str:
    if address and city:
        return f"{address}, {city}"
    if address:
        return address
    if city:
        return city
    return "n/a"


def _land_use_label(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "Unknown use"
    match = re.match(r"^\(([^)]+)\)\s*(.*)$", text)
    return match.group(2).strip() if match and match.group(2).strip() else text


def _zone_definition(zone_id: Any, zone_name: Any, row: dict[str, Any]) -> str:
    parts = []
    if zone_name:
        parts.append(str(zone_name))
    if row.get("comp_plan_lud"):
        parts.append(f"Comprehensive plan: {row['comp_plan_lud']}")
    if row.get("zoning_code"):
        parts.append(f"Source zoning code: {row['zoning_code']}")
    if zone_id and zone_id != zone_name:
        parts.append(f"Short code: {zone_id}")
    return ". ".join(parts) or "No zoning definition is available for this parcel."


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value
