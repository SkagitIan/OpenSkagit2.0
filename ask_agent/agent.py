from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import requests

from context_mcp import services as context_services

from .duck import connect, database_path

READ_ONLY_TABLES = {
    "assessor_rollup",
    "improvements",
    "land",
    "sales",
    "code_descriptions",
    "code_mappings",
    "primary_use_codes",
}

ANALYSIS_RULES = """
Default OpenSkagit analysis rules:
- For market value, regression, comparable-sale, and IAAO analysis, use only valid sales unless the user explicitly asks otherwise.
  SQL: sales.sale_type = 'VALID SALE'
- For residential property analysis, filter assessor_rollup.proptype = 'R'.
  Residential means homes, houses, SFR, condos, residential neighborhoods, or dwelling-focused questions.
- For commercial property analysis, filter assessor_rollup.proptype = 'C'.
  Commercial means retail, office, industrial, business, income property, or commercial-use questions.
- For recent sales, default to sales.sale_date_iso >= '2024-01-01' unless the user provides a different date range.
- Prefer exact mapped codes from code_mappings over text matching descriptions.
- If applying one of these defaults would materially change the analysis and the user's intent is ambiguous, state the default in the answer.
""".strip()


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]


@dataclass
class AnalysisResponse:
    answer: str
    result: QueryResult | None = None
    sql: str | None = None
    reality_checks: list[str] | None = None


@dataclass(frozen=True)
class ResolvedTerm:
    category: str
    code: str
    description: str
    filter_expression: str
    display_column: str


CODE_FILTERS = {
    "improvement_type": ("improvements.imprv_det_type_cd", "improvements.imprv_det_type_description"),
    "improvement_class": ("improvements.imprv_det_class_cd", "improvements.imprv_det_class_description"),
    "condition": ("improvements.condition_cd", "improvements.condition_description"),
    "land_use": ("assessor_rollup.land_use_code", "assessor_rollup.land_use_description"),
    "neighborhood": ("assessor_rollup.neighborhood_code_id", "assessor_rollup.neighborhood_description"),
    "utilities": ("assessor_rollup.utilities_codes", "assessor_rollup.utilities_description"),
}

LAND_USE_ALIASES = {
    "910": {
        "rec lot", "rec lots", "recreational lot", "recreational lots",
        "recreation lot", "recreation lots", "unimproved", "unimproved land",
        "undeveloped", "undeveloped land", "vacant lot", "vacant lots", "raw land",
    },
    "190": {"vacation cabin", "vacation cabins", "cabin lot", "cabin lots"},
    "740": {"recreational activities", "recreational activity"},
}

DEFAULT_OPENSKAGIT_MCP_URL = "https://skagit-agent-worker.ian-larsen-1976.workers.dev/mcp"

STREET_SUFFIXES = {
    "aly", "alley", "ave", "avenue", "blvd", "boulevard", "cir", "circle",
    "ct", "court", "dr", "drive", "hwy", "highway", "ln", "lane", "loop",
    "pl", "place", "rd", "road", "st", "street", "ter", "terrace", "trl",
    "trail", "way",
}


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _call_openskagit_mcp_tool(
    name: str,
    arguments: dict[str, Any],
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Call the Cloudflare Worker MCP JSON-RPC endpoint and return the tool payload."""
    if not _env_enabled("OPENSKAGIT_ENABLE_MCP", default=True):
        raise RuntimeError("OpenSkagit MCP tools are disabled by OPENSKAGIT_ENABLE_MCP=false.")

    url = os.environ.get("OPENSKAGIT_MCP_URL", DEFAULT_OPENSKAGIT_MCP_URL).strip()
    if not url:
        raise RuntimeError("OPENSKAGIT_MCP_URL is empty.")

    headers = {"content-type": "application/json"}
    token = os.environ.get("OPENSKAGIT_MCP_BEARER_TOKEN", "").strip()
    if token:
        headers["authorization"] = f"Bearer {token}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    timeout = timeout_seconds if timeout_seconds is not None else float(os.environ.get("OPENSKAGIT_MCP_TIMEOUT_SECONDS", "60"))
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    message = response.json()
    if "error" in message:
        error = message["error"]
        raise RuntimeError(error.get("message", str(error)) if isinstance(error, dict) else str(error))

    result = message.get("result", {})
    content = result.get("content", [])
    if content and isinstance(content[0], dict) and content[0].get("type") == "text":
        import json

        text = content[0].get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
    return {"result": result}


def schema_summary(db_path: Path | None = None, conn: duckdb.DuckDBPyConnection | None = None) -> str:
    db_path = db_path or database_path()
    close_when_done = conn is None
    active = conn or connect(db_path, read_only=True)
    try:
        parts: list[str] = [
            "This is a DuckDB database of Skagit County public records. Use the *_description columns for human-readable analysis. Do not infer meanings from raw codes when mapped columns exist.",
            "",
            "assessor_rollup key columns:",
            "parcel_number, legal_description, situs_street_name, situs_city_state_zip, owner_name, owner_city, owner_state, owner_zip, "
            "neighborhood_code_id, neighborhood_description, land_use_code, land_use_description, utilities_codes, utilities_description, "
            "assessed_value_num, taxable_value_num, total_market_value_num, acres_num, sale_price_num, sale_date_iso, year_built, living_area",
            "",
            "improvements key columns:",
            "parcelnumber, description, building_style, comment, imprv_det_type_cd, imprv_det_type_description, "
            "imprv_det_class_cd, imprv_det_class_description, condition_cd, condition_description, calc_area, "
            "imprv_val_num, living_area_num, actual_year_built, effective_yr_blt",
            "",
            "land key columns:",
            "parcelnumber, land_type, appr_meth, size_acres_num, market_value_num, open_space_use_code_desc, land_seg_comment",
            "",
            "sales key columns:",
            "parcel_number, seller_name, buyer_name, sale_price_num, sale_date_iso, sale_type, deed_type, reval_area",
            "",
            "code_mappings columns:",
            "category, code, description, source. Categories include improvement_type, improvement_class, condition, land_use, neighborhood, utilities.",
            "",
            "Analysis guidance:",
            "- You may use SELECT/WITH and CREATE TEMP TABLE/VIEW ... AS SELECT for multi-step analysis.",
            "- Prefer mapped code filters from the analysis context. For example, use imprv_det_type_cd = 'AGAR' for attached garage when that mapping is present.",
            "- For land-use intent, inspect code_mappings category land_use and filter on assessor_rollup.land_use_code when an exact county code applies.",
            "- For IAAO-style fairness checks, use valid recent sales, sale-to-assessed ratios, medians, dispersion, and neighborhood cohorts.",
            "",
            "Mapping guidance:",
            "- Rec lots, vacant lots, undeveloped land, and unimproved land should use land_use_code = '910' when the county mapping is present.",
            "- Vacation/cabin property should use land_use_code = '190' when the county mapping is present.",
            "- Do not infer physical land features from designations such as TREES or FOREST unless the user explicitly asks for forestry/open-space designations.",
            "- Public sewer/power/water should use utilities_description LIKE '%Sewer%', '%Power%', '%Public water%' instead of raw markers like *SEW.",
            "- Neighborhood filtering should use neighborhood_code_id or neighborhood_description, not the raw neighborhood_code field.",
            "- Join assessor_rollup.parcel_number to improvements.parcelnumber or land.parcelnumber when detail tables are needed.",
        ]
        try:
            mapping_examples = active.execute(
                """
                SELECT category, code, description
                FROM code_mappings
                WHERE category IN ('utilities', 'condition')
                   OR code IN ('AGAR', 'CCP', 'MSA', 'MSG', '190', '740', '910')
                ORDER BY category, code
                LIMIT 80
                """
            ).fetchall()
        except duckdb.Error:
            mapping_examples = []
        if mapping_examples:
            parts.append("")
            parts.append("Useful mapping examples:")
            parts.extend(f"{row[0]}:{row[1]} = {row[2]}" for row in mapping_examples)
        return "\n".join(parts)
    finally:
        if close_when_done:
            active.close()


def analysis_context(
    question: str,
    db_path: Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> str:
    resolved = resolve_terms(question, db_path, conn=conn)
    relevant_definitions = relevant_code_definitions(question, db_path, conn=conn)
    parts = [
        schema_summary(db_path, conn=conn),
        "",
        ANALYSIS_RULES,
        "",
        "Resolved mapping terms from code_mappings:",
    ]
    if resolved:
        for term in resolved:
            parts.append(
                f"- {term.category}:{term.code} = {term.description}; "
                f"preferred filter: {term.filter_expression}; display: {term.display_column}"
            )
    else:
        parts.append("- None found. Use schema columns directly and avoid inventing codes.")
    if relevant_definitions:
        parts.extend(
            [
                "",
                "Relevant code definitions from code_mappings:",
            ]
        )
        parts.extend(
            f"- {term.category}:{term.code} = {term.description}; filter: {term.filter_expression}"
            for term in relevant_definitions
        )
    parts.extend(
        [
            "",
            "Required planning step before SQL:",
            "- Translate the user request into tables, joins, filters, metrics, and assumptions.",
            "- If a resolved mapping term exists, use its preferred code filter instead of text-searching descriptions.",
            "- Ask one focused follow-up only when a missing choice materially changes the result.",
            "- Otherwise choose a conservative default and state it in the answer.",
            "",
            "Reality-check expectations after query execution:",
            "- Mention small sample sizes, empty comparison groups, null-heavy fields, duplicate sale risk, and approximate validity filters.",
            "- Do not overstate grouped comparisons as full regressions.",
        ]
    )
    return "\n".join(parts)


def relevant_code_definitions(
    question: str,
    db_path: Path | None = None,
    limit: int = 140,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[ResolvedTerm]:
    categories = _contextual_mapping_categories(question)
    if not categories:
        return []

    db_path = db_path or database_path()
    close_when_done = conn is None
    active = conn or connect(db_path, read_only=True)
    try:
        try:
            rows = active.execute(
                """
                SELECT category, code, description
                FROM code_mappings
                WHERE category IN (SELECT unnest(?))
                ORDER BY category, code
                LIMIT ?
                """,
                (categories, limit),
            ).fetchall()
        except duckdb.Error:
            return []
    finally:
        if close_when_done:
            active.close()

    definitions: list[ResolvedTerm] = []
    for category, code, description in rows:
        if category not in CODE_FILTERS or not code or not description:
            continue
        code_column, _display_column = CODE_FILTERS[str(category)]
        definitions.append(
            ResolvedTerm(
                category=str(category),
                code=str(code),
                description=str(description),
                filter_expression=_mapping_filter_expression(str(category), code_column, str(code)),
                display_column=CODE_FILTERS[str(category)][1],
            )
        )
    return definitions


def _contextual_mapping_categories(question: str) -> list[str]:
    tokens = set(_tokens(question))
    categories: list[str] = []
    if tokens & {"land", "lot", "lots", "parcel", "parcels", "use", "vacation", "cabin", "rec", "recreational", "unimproved", "undeveloped", "vacant", "forest", "trees"}:
        categories.append("land_use")
    if tokens & {"utility", "utilities", "sewer", "power", "water", "well", "septic"}:
        categories.append("utilities")
    if tokens & {"neighborhood", "area", "city"}:
        categories.append("neighborhood")
    return categories


def resolve_terms(
    question: str,
    db_path: Path | None = None,
    limit: int = 12,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[ResolvedTerm]:
    db_path = db_path or database_path()
    normalized_question = _normalize_for_match(question)
    question_tokens = set(_tokens(question))
    close_when_done = conn is None
    active = conn or connect(db_path, read_only=True)
    try:
        try:
            rows = active.execute(
                """
                SELECT category, code, description
                FROM code_mappings
                ORDER BY
                    CASE WHEN source = 'manual' THEN 0 ELSE 1 END,
                    LENGTH(description) DESC,
                    category,
                    code
                """
            ).fetchall()
        except duckdb.Error:
            return []
    finally:
        if close_when_done:
            active.close()

    matches: list[tuple[int, ResolvedTerm]] = []
    seen: set[tuple[str, str]] = set()
    for category, code, description in rows:
        if category not in CODE_FILTERS or not code or not description:
            continue
        score = _mapping_match_score(str(category), normalized_question, question_tokens, str(code), str(description))
        if score <= 0:
            continue
        key = (str(category), str(code))
        if key in seen:
            continue
        seen.add(key)
        code_column, display_column = CODE_FILTERS[str(category)]
        matches.append(
            (
                score,
                ResolvedTerm(
                    category=str(category),
                    code=str(code),
                    description=str(description),
                    filter_expression=_mapping_filter_expression(str(category), code_column, str(code)),
                    display_column=display_column,
                ),
            )
        )

    matches.sort(key=lambda item: (-item[0], item[1].category, item[1].code))
    return [term for _, term in matches[:limit]]


def _mapping_filter_expression(category: str, code_column: str, code: str) -> str:
    escaped = code.replace("'", "''")
    if category == "utilities":
        return f"contains(string_split({code_column}, ', '), '{escaped}')"
    return f"{code_column} = '{escaped}'"


def _mapping_match_score(category: str, question: str, question_tokens: set[str], code: str, description: str) -> int:
    code_norm = _normalize_for_match(code)
    desc_norm = _normalize_for_match(description)
    desc_tokens = _tokens(description)
    alias_score = _land_use_alias_score(question, code) if category == "land_use" else 0
    if alias_score:
        return alias_score
    if _looks_like_street_address_tokens(question_tokens) and code_norm.isdigit():
        return 0
    if code_norm and re.search(rf"(?<![a-z0-9]){re.escape(code_norm)}(?![a-z0-9])", question):
        return 100
    if len(desc_norm) >= 3 and desc_norm in question:
        return 90 + min(len(desc_tokens), 9)
    if 1 < len(desc_tokens) <= 4 and all(len(token) >= 3 for token in desc_tokens) and set(desc_tokens).issubset(question_tokens):
        return 70 + len(desc_tokens)
    return 0


def _land_use_alias_score(question: str, code: str) -> int:
    aliases = LAND_USE_ALIASES.get(code)
    if not aliases:
        return 0
    for alias in aliases:
        alias_norm = _normalize_for_match(alias)
        if alias_norm and re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", question):
            return 95
    return 0


def _normalize_for_match(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _looks_like_street_address_tokens(tokens: set[str]) -> bool:
    return bool(tokens & STREET_SUFFIXES) and any(token.isdigit() for token in tokens)


def _extract_address_query(question: str) -> str | None:
    tokens = _tokens(question)
    if not _looks_like_street_address_tokens(set(tokens)):
        return None

    start = next((index for index, token in enumerate(tokens) if token.isdigit()), None)
    if start is None:
        return None

    stop = len(tokens)
    for index in range(start + 1, len(tokens)):
        if tokens[index] in {"in", "near", "around", "with", "and", "please"}:
            stop = index
            break
        if tokens[index] in STREET_SUFFIXES:
            stop = index + 1
            break

    address_tokens = tokens[start:stop]
    if len(address_tokens) < 3 or not any(token in STREET_SUFFIXES for token in address_tokens):
        return None
    return " ".join(address_tokens)


def _parcel_search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("results", "parcels", "matches", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("result"), dict):
        return _parcel_search_results(payload["result"])
    return []


def _parcel_id_from_search_result(row: dict[str, Any]) -> str | None:
    for key in ("parcel", "parcel_number", "parcelNumber", "parcel_id", "id"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def _address_lookup_context(question: str) -> str | None:
    address_query = _extract_address_query(question)
    if not address_query or not _env_enabled("OPENSKAGIT_ENABLE_MCP", default=True):
        return None

    try:
        timeout = float(os.environ.get("OPENSKAGIT_ADDRESS_PREFLIGHT_TIMEOUT_SECONDS", "12"))
        payload = _call_openskagit_mcp_tool("search_parcels", {"q": address_query}, timeout_seconds=timeout)
    except Exception as exc:
        return (
            f"Address preflight: attempted search_parcels({address_query!r}) before analysis, "
            f"but the lookup failed with {type(exc).__name__}: {exc}. Try search_parcels again before answering."
        )

    results = _parcel_search_results(payload)
    if not results:
        return (
            f"Address preflight: search_parcels({address_query!r}) returned no parcel matches. "
            "Before saying no records exist, try a normalized address variant and then explain the lookup attempt."
        )

    first_parcel = _parcel_id_from_search_result(results[0])
    lines = [
        f"Address preflight: the user appears to be asking about the address {address_query!r}.",
        f"search_parcels({address_query!r}) returned {len(results)} candidate parcel match(es).",
    ]
    if first_parcel:
        lines.append(
            f"Use parcel {first_parcel} first for parcel-specific tools such as get_property_context or get_property_summary."
        )
    lines.append(f"Top search result payload: {results[0]}")
    lines.append("Do not interpret the street number as a neighborhood, land-use, utility, or other county code.")
    return "\n".join(lines)


def execute_readonly_sql(sql: str, limit: int = 200, db_path: Path | None = None) -> QueryResult:
    if not is_safe_select(sql):
        raise ValueError("Only a single read-only SELECT query is allowed.")
    db_path = db_path or database_path()
    conn = connect(db_path, read_only=True)
    try:
        return _execute_select(conn, sql, limit)
    finally:
        conn.close()


def execute_analysis_sql(
    sql: str,
    limit: int = 200,
    db_path: Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> QueryResult:
    if not is_safe_analysis_sql(sql):
        raise ValueError("Only SELECT/WITH, CREATE TEMP TABLE/VIEW ... AS SELECT, and DROP of temp_ or analysis_ objects are allowed.")
    close_when_done = conn is None
    active = conn or connect(db_path or database_path(), read_only=is_safe_select(sql))
    try:
        stripped = _strip_sql(sql)
        if is_safe_select(stripped):
            return _execute_select(active, stripped, limit)
        cursor = active.execute(stripped)
        if cursor.description:
            return _cursor_to_result(cursor, limit)
        return QueryResult(columns=["status"], rows=[{"status": "Analysis statement completed."}])
    finally:
        if close_when_done:
            active.close()


def _execute_select(conn: duckdb.DuckDBPyConnection, sql: str, limit: int) -> QueryResult:
    wrapped = f"SELECT * FROM ({_strip_sql(sql)}) LIMIT ?"
    cursor = conn.execute(wrapped, (limit,))
    return _cursor_to_result(cursor, limit)


def _cursor_to_result(cursor: duckdb.DuckDBPyConnection, limit: int) -> QueryResult:
    columns = [column[0] for column in cursor.description] if cursor.description else []
    rows = cursor.fetchmany(limit)
    return QueryResult(columns=columns, rows=[dict(zip(columns, row)) for row in rows])


def result_reality_checks(result: QueryResult | None) -> list[str]:
    if result is None:
        return ["No query result was produced."]
    if not result.rows:
        return ["The query returned no rows; filters may be too narrow or joins may have removed all records."]

    warnings: list[str] = []
    row_count = len(result.rows)
    if row_count < 10:
        warnings.append(f"Only {row_count} result rows were returned; treat conclusions as directional.")

    for column in result.columns:
        null_count = sum(1 for row in result.rows if row.get(column) in (None, ""))
        if row_count and null_count / row_count >= 0.3:
            warnings.append(f"Column {column} is null or blank in at least 30% of returned rows.")

    for price_column in ["sale_price_num", "median_sale_price", "avg_sale_price"]:
        if price_column not in result.columns:
            continue
        values = [
            row.get(price_column)
            for row in result.rows
            if isinstance(row.get(price_column), int | float)
        ]
        if values and (min(values) <= 0 or max(values) > 10_000_000):
            warnings.append(f"Column {price_column} has values outside a normal residential sale range.")

    return warnings[:6]


def is_safe_select(sql: str) -> bool:
    stripped = _strip_sql(sql)
    if not re.match(r"(?is)^(select|with)\b", stripped):
        return False
    if ";" in stripped:
        return False
    forbidden = r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|copy|install|load|export|import)\b"
    return re.search(forbidden, stripped, flags=re.IGNORECASE) is None


def is_safe_analysis_sql(sql: str) -> bool:
    stripped = _strip_sql(sql)
    if not stripped or ";" in stripped:
        return False
    if is_safe_select(stripped):
        return True
    if re.match(r"(?is)^create\s+(temporary|temp)\s+(table|view)\s+[a-z_][a-z0-9_]*\s+as\s+(select|with)\b", stripped):
        return not _contains_persistent_mutation(stripped)
    drop_match = re.match(r"(?is)^drop\s+(table|view)\s+(if\s+exists\s+)?([a-z_][a-z0-9_]*)$", stripped)
    if drop_match:
        name = drop_match.group(3).lower()
        return name.startswith("analysis_") or name.startswith("temp_")
    return False


def _contains_persistent_mutation(sql: str) -> bool:
    forbidden = r"\b(insert|update|delete|alter|attach|detach|pragma|vacuum|copy|install|load|export|import)\b"
    if re.search(forbidden, sql, flags=re.IGNORECASE):
        return True
    return bool(re.search(r"(?is)\bcreate\s+(?!temporary\b|temp\b)", sql))


def _strip_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def answer_question(question: str) -> AnalysisResponse:
    try:
        from agents import Agent, MaxTurnsExceeded, Runner, function_tool
    except Exception:
        return AnalysisResponse(
            "The OpenAI Agents SDK is not installed. Run: pip install openai-agents  "
            "then set OPENAI_API_KEY in .env and try again.",
            None,
        )

    if not os.environ.get("OPENAI_API_KEY"):
        return AnalysisResponse(
            "OPENAI_API_KEY is not set. Add it to .env to enable AI analysis.",
            None,
        )

    db_path = database_path()
    last_result: QueryResult | None = None
    last_sql: str | None = None
    address_context = _address_lookup_context(question)
    try:
        analysis_conn = connect(db_path)
    except Exception as exc:
        if address_context:
            return AnalysisResponse(
                "I found an address-style query, but the analytical database connection failed before I could build the full answer. "
                f"{address_context}\n\nDatabase error: {type(exc).__name__}: {exc}",
                None,
            )
        return AnalysisResponse(
            f"Analysis failed before querying records: {type(exc).__name__}: {exc}",
            None,
        )
    resolved_terms = resolve_terms(question, db_path, conn=analysis_conn)

    @function_tool
    def get_analysis_context() -> str:
        """Return DuckDB schema, resolved code_mappings terms, and planning rules for this question."""
        return analysis_context(question, db_path, conn=analysis_conn)

    @function_tool
    def run_analysis_query(sql: str) -> dict[str, Any]:
        """Run a guarded DuckDB analysis statement. Allows SELECT and CREATE TEMP TABLE/VIEW AS SELECT."""
        nonlocal last_result, last_sql
        last_sql = sql
        last_result = execute_analysis_sql(sql, db_path=db_path, conn=analysis_conn)
        checks = result_reality_checks(last_result)
        return {
            "columns": last_result.columns,
            "row_count": len(last_result.rows),
            "rows": last_result.rows,
            "reality_checks": checks,
            "instruction": "Use these rows and reality checks to continue the analysis or answer. Keep tool calls focused.",
        }

    @function_tool
    def search_parcels(q: str) -> dict[str, Any]:
        """MCP: Search Skagit County parcels by address text or parcel number."""
        return _call_openskagit_mcp_tool("search_parcels", {"q": q})

    @function_tool
    def get_property_context(
        parcel: str,
        raw: bool = False,
        bundles: str | None = None,
        layers: str | None = None,
    ) -> dict[str, Any]:
        """MCP: Get a full parcel context packet with property summary and GIS overlays."""
        args: dict[str, Any] = {"parcel": parcel, "raw": raw}
        if bundles:
            args["bundles"] = bundles
        if layers:
            args["layers"] = layers
        return _call_openskagit_mcp_tool("get_property_context", args)

    @function_tool
    def get_property_summary(parcel: str, raw: bool = False) -> dict[str, Any]:
        """MCP: Get parsed assessor/property context for one parcel without GIS overlays."""
        return _call_openskagit_mcp_tool("get_property_summary", {"parcel": parcel, "raw": raw})

    @function_tool
    def get_gis_overlays(
        parcel: str,
        bundles: str | None = None,
        layers: str | None = None,
    ) -> dict[str, Any]:
        """MCP: Get GIS overlays intersecting a parcel."""
        args: dict[str, Any] = {"parcel": parcel}
        if bundles:
            args["bundles"] = bundles
        if layers:
            args["layers"] = layers
        return _call_openskagit_mcp_tool("get_gis_overlays", args)

    @function_tool
    def get_census_context(parcel: str) -> dict[str, Any]:
        """Get Census ACS area-level context from the canonical same-process service."""
        return context_services.get_census_context(parcel)

    @function_tool
    def get_soils_context(parcel: str) -> dict[str, Any]:
        """Get NRCS SSURGO soil map units from the canonical same-process service."""
        return context_services.get_soils_context(parcel)

    @function_tool
    def list_gis_layers() -> dict[str, Any]:
        """MCP: List available GIS overlay bundles and layer keys."""
        return _call_openskagit_mcp_tool("list_gis_layers", {})

    model = os.environ.get("OPENAI_MODEL", "gpt-4.1")
    tools = [get_analysis_context, run_analysis_query]
    if _env_enabled("OPENSKAGIT_ENABLE_MCP", default=True):
        tools.extend([
            search_parcels,
            get_property_context,
            get_property_summary,
            get_gis_overlays,
            get_census_context,
            get_soils_context,
            list_gis_layers,
        ])
    agent = Agent(
        name="OpenSkagit DuckDB analyst",
        model=model,
        instructions=(
            "You analyze Skagit County public records using DuckDB and live OpenSkagit MCP tools. "
            "DuckDB contains assessor, property, permit, sale, and related tabular county data. "
            "Call get_analysis_context once before querying to understand the schema and available code mappings. "
            "First make an internal structured plan: resolved terms, tables, joins, filters, metrics, and assumptions. "
            "If a resolved mapping term is present, use its preferred code filter; do not text-search its description. "
            "You may run multiple guarded analysis queries. "
            "Allowed SQL: SELECT/WITH, CREATE TEMP TABLE/VIEW ... AS SELECT, and dropping temp_ or analysis_ objects. "
            "Never modify persistent tables. Always prefer mapped readable fields such as land_use_description, "
            "neighborhood_description, utilities_description, imprv_det_type_description, and condition_description. "
            "Use DuckDB for cohort analysis, rollups, sales ratios, comparable-sale summaries, and questions that need "
            "many parcels or historical tabular records. "
            "Use the OpenSkagit Cloudflare MCP compatibility tools for live parcel lookup, parcel-specific property dossiers, "
            "GIS overlays, and ArcGIS layer metadata. Census and soils use canonical same-process services backed by PostGIS "
            "parcel geometry. If the user gives an address, use search_parcels before parcel-specific tools. "
            "If an Address preflight note is included in the user message, rely on it before DuckDB code mappings. "
            "Do not treat reval area as a neighborhood. Census values are area-level estimates, not parcel-level facts. "
            "For regression-style questions, compute transparent DuckDB aggregates and explain limitations. "
            "Answer from query results, keep answers concise, and state your assumptions."
        ),
        tools=tools,
    )
    try:
        agent_input = question
        if address_context:
            agent_input = f"{question}\n\n{address_context}"
        result = Runner.run_sync(agent, agent_input, max_turns=20)
    except MaxTurnsExceeded:
        if last_result is not None:
            return AnalysisResponse(
                "The agent ran too many tool steps; here are the latest query results. "
                "Try asking a narrower question.",
                last_result,
                last_sql,
                result_reality_checks(last_result),
            )
        return AnalysisResponse(
            "The agent ran too many steps without producing an answer. Try a narrower question.",
            None,
        )
    except Exception as exc:
        return AnalysisResponse(
            f"Analysis failed: {type(exc).__name__}: {exc}",
            last_result,
            last_sql,
            result_reality_checks(last_result),
        )
    finally:
        analysis_conn.close()

    checks = result_reality_checks(last_result)
    footer_parts: list[str] = []
    if resolved_terms:
        footer_parts.append(
            "Resolved mappings: "
            + ", ".join(f"{term.category}:{term.code} ({term.description})" for term in resolved_terms[:5])
        )
    if last_sql:
        footer_parts.append("Reality checks: " + " ".join(checks))
    footer = "\n\n" + "\n".join(footer_parts) if footer_parts else ""
    return AnalysisResponse(str(result.final_output) + footer, last_result, last_sql, checks)
