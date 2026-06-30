from __future__ import annotations

import copy
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.db import DatabaseError, close_old_connections, connection, transaction

from .models import OpportunitySearch, OpportunitySearchFeedback
from .services import (
    _base_row,
    _fetch,
    feature_labels,
    is_natural_resource_zone,
    is_public_or_civic_land_use,
    is_public_or_open_space_zone,
    is_resource_land_use,
    mark_saved,
    risk_flags,
    utility_labels,
)


DEFAULT_RESULT_LIMIT = 200
FEEDBACK_REASONS = OpportunitySearchFeedback.REASON_CHOICES
_ACTIVE_SEARCH_IDS: set[int] = set()
_ACTIVE_SEARCH_LOCK = threading.Lock()
RESIDENTIAL_DWELLING_CODES = {"110", "111", "112", "113", "120", "130", "180", "181", "182", "185", "190"}
NONRESIDENTIAL_LAND_USE_PREFIXES = ("2", "3", "4", "5", "6", "7", "8")
BARE_RECREATION_TERMS = {"bare", "raw", "unimproved", "undeveloped", "recreation", "recreational", "camp", "camping"}
LAND_ASSET_TERMS = {"land", "lot", "lots", "parcel", "parcels", "acreage", "acres"}
MULTIUNIT_TERMS = {"duplex", "triplex", "fourplex", "fiveplex", "sixplex", "multiunit", "multifamily", "multi", "unit", "units"}
AVERAGE_QUALITY_TERMS = {"average", "avg"}
ZONING_INTENT_TERMS = {
    "adu",
    "adult",
    "allowed",
    "assisted",
    "camp",
    "campground",
    "community",
    "conditional",
    "conversion",
    "convert",
    "development",
    "duplex",
    "feasible",
    "feasibility",
    "fourplex",
    "industrial",
    "multifamily",
    "permitted",
    "possible",
    "recreation",
    "recreational",
    "redevelopment",
    "senior",
    "sixplex",
    "suitable",
    "triplex",
    "use",
    "uses",
    "zoned",
    "zoning",
}
BAD_BARE_LAND_TEXT = (
    "MH LEASED",
    "LEASED PROPERTY",
    "CONDO",
    "CONDOMINIUM",
    "COMMON AREA",
    "PUBLIC",
    "GOVERNMENT",
    "SCHOOL",
    "CHURCH",
    "CEMETERY",
    "MOORAGE",
)
DWELLING_ASSET_TERMS = {
    "home",
    "homes",
    "house",
    "houses",
    "sfr",
    "dwelling",
    "dwellings",
    "residence",
    "residences",
    "residential",
}
EXPLICIT_NONRESIDENTIAL_TERMS = {
    "commercial",
    "retail",
    "restaurant",
    "restaurants",
    "industrial",
    "church",
    "churches",
    "government",
    "office",
    "warehouse",
    "institutional",
}

ALLOWED_TABLES = {
    "assessor_rollup",
    "code_mappings",
    "gis_skagit_parcels",
    "improvements",
    "land",
    "land_ledger_parcels",
    "parcel_primary_zoning",
    "parcel_zoning",
    "sales",
    "skagit_parcel_history",
    "skagit_parcels",
    "tax_delinquency_taxstatement",
    "v_land_ledger_source",
    "v_parcel_tax_detail",
    "v_parcel_tax_summary",
    "waza_zoning_zones",
}

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze|attach|detach|call|do|execute)\b",
    re.IGNORECASE,
)

SCHEMA_CONTEXT = """
Exact core columns:
- skagit_parcels p: parcel_number, account_number, situs_street_number, situs_street_name, situs_city_state_zip, owner_name, building_value, land_use, impr_land_value, unimpr_land_value, assessed_value, taxable_value, total_market_value, acres, total_taxes, inactive_date, city_district, utilities, year_built, living_area, sale_date, sale_price, sale_deed_type
- gis_skagit_parcels g: parcel_id, citydistrict, acres, geometry
- parcel_primary_zoning z: parcel_id, citydistrict, acres, jurisdiction, zone_id, zone_name, waza_general, waza_specific, reference_url
- assessor_rollup ar: parcel_number, land_use_code, land_use_description, neighborhood_code_id, neighborhood_description, utilities_codes, utilities_description
- improvements i: parcelnumber, imprv_det_type_cd, imprv_det_type_description, imprv_det_class_cd, imprv_det_class_description, condition_cd, condition_description, imprv_val_num, living_area_num, actual_year_built, effective_yr_blt
- land l: parcelnumber, land_type, appr_meth, size_acres_num, market_value_num, effective_front, actual_front
- sales s: parcel_number, sale_price_num, sale_date_iso, sale_type, deed_type, buyer_name, seller_name
- tax_delinquency_taxstatement t: parcel_number, tax_year, total_due, amount_paid, status, lead_level, delinquent_installment_count, unpaid_installment_count, oldest_due_date

Never use columns not listed here. In particular, parcel_primary_zoning does not have primary_zone; use z.zone_id, z.zone_name, z.waza_general, or z.waza_specific.
sales.sale_date_iso is a text ISO-date field. For date comparisons, guard and cast it: NULLIF(s.sale_date_iso, '')::date, preferably with s.sale_date_iso ~ '^\\d{4}-\\d{2}-\\d{2}$'.
""".strip()

FALLBACK_SKILL_REFERENCE_CONTEXT = """
OpenSkagit data dictionary essentials:
- Use raw assessor codes and readable labels together when possible.
- `skagit_parcels.land_use` commonly includes code and label, for example `(111) HOUSEHOLD, SFR, INSIDE CITY`, `(181) MH LEASED PROPERTY`, `(911) UNDEVELOPED LAND INCORPORATED`.
- Parse land-use code with split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1).
- Key land-use meanings: 110/111/112/113 SFR/household; 120/130 multi-unit; 140 condo residential; 150 mobile home parks; 180 manufactured homes; 181 MH leased property; 182 multiple mobile homes; 185 MH with detached SFR; 190 vacation/cabin; 670 governmental; 680 schools; 740 recreational activities; 760 parks; 910 unimproved land; 911 undeveloped incorporated land; 912 undeveloped 2-4 family; 930 water areas; 940 open space; 970 condo moorage.
- MH LEASED PROPERTY is not bare land; leased manufactured homes may exist without normal main-area dwelling improvements.
- Utilities tokens: PWR power, PWR-U underground power, SEP septic, SEW sewer, WTR-P public water, WTR-W well water, NONE no listed utilities.
- Improvements: MA is common main-area dwelling; MA2/MA1.5F/UF2/UF1.5F/BMF/BMU/BMG also indicate dwelling/living-area evidence. Prefer `imprv_det_type_description`, `imprv_det_class_description`, and `condition_description` when available.
- Land table clues: `land.land_type` includes CLEARED, WOODED/BRUSH, TIMBER, TIDELAND, WET; `land.appr_meth` includes ACREAGE, LOT, SQUARE FOOT, Front Foot.
- `assessor_rollup` has land_use_description, neighborhood_description, and utilities_description for human-readable labels.
""".strip()


@dataclass(frozen=True)
class GeneratedSearch:
    title: str
    criteria_summary: str
    assumptions: list[str]
    sql: str
    params: list[Any]


@dataclass(frozen=True)
class SearchPlan:
    title: str
    criteria_summary: str
    asset_intent: str
    location: dict[str, Any]
    hard_filters: list[str]
    soft_rankers: list[str]
    exclusions: list[str]
    assumptions: list[str]
    relaxation_order: list[str]
    needs_zoning_definitions: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "criteria_summary": self.criteria_summary,
            "asset_intent": self.asset_intent,
            "location": self.location,
            "hard_filters": self.hard_filters,
            "soft_rankers": self.soft_rankers,
            "exclusions": self.exclusions,
            "assumptions": self.assumptions,
            "relaxation_order": self.relaxation_order,
            "needs_zoning_definitions": self.needs_zoning_definitions,
        }


class OpportunitySearchError(ValueError):
    pass


def start_ai_opportunity_search(user, prompt: str) -> OpportunitySearch:
    prompt = (prompt or "").strip()
    if not prompt:
        raise OpportunitySearchError("Enter a natural-language search first.")

    search = OpportunitySearch.objects.create(user=user, prompt=prompt, status=OpportunitySearch.STATUS_DRAFT)
    transaction.on_commit(lambda: _start_ai_search_worker(search.pk))
    return search


def start_refresh_opportunity_search(search: OpportunitySearch) -> OpportunitySearch:
    search.status = OpportunitySearch.STATUS_DRAFT
    search.error = ""
    search.save(update_fields=["status", "error", "updated_at"])
    transaction.on_commit(lambda: _start_ai_search_worker(search.pk))
    return search


def ensure_ai_search_worker(search: OpportunitySearch) -> None:
    if search.status == OpportunitySearch.STATUS_DRAFT:
        _start_ai_search_worker(search.pk)


def _start_ai_search_worker(search_id: int) -> None:
    with _ACTIVE_SEARCH_LOCK:
        if search_id in _ACTIVE_SEARCH_IDS:
            return
        _ACTIVE_SEARCH_IDS.add(search_id)
    worker = threading.Thread(target=_run_ai_search_worker, args=(search_id,), daemon=True)
    worker.start()


def _run_ai_search_worker(search_id: int) -> None:
    close_old_connections()
    try:
        search = OpportunitySearch.objects.select_related("user").get(pk=search_id)
        refresh_opportunity_search(search)
    except Exception as exc:
        OpportunitySearch.objects.filter(pk=search_id).update(
            status=OpportunitySearch.STATUS_ERROR,
            error=_friendly_error(exc)[:2000],
            result_rows=[],
            result_count=0,
        )
    finally:
        close_old_connections()
        with _ACTIVE_SEARCH_LOCK:
            _ACTIVE_SEARCH_IDS.discard(search_id)


def run_ai_opportunity_search(user, prompt: str, search: OpportunitySearch | None = None) -> OpportunitySearch:
    prompt = (prompt or "").strip()
    if not prompt:
        raise OpportunitySearchError("Enter a natural-language search first.")

    search = search or OpportunitySearch.objects.create(user=user, prompt=prompt)
    search.prompt = prompt
    search.status = OpportunitySearch.STATUS_DRAFT
    search.error = ""
    search.save(update_fields=["prompt", "status", "error", "updated_at"])

    model = _search_model()
    if not os.environ.get("OPENAI_API_KEY"):
        return _mark_error(search, "OPENAI_API_KEY is not set. Add it to .env to enable AI opportunity search.", model)

    plan = _fallback_search_plan(prompt)
    plan_review: dict[str, Any] = {"source": "deterministic", "changes": [], "warnings": []}
    generated: GeneratedSearch | None = None
    result_rows: list[dict[str, Any]] = []
    result_diagnostics: dict[str, Any] = {}
    try:
        plan = _review_search_plan(prompt, _generate_search_plan(prompt, model), model)
        plan_review = {
            "source": "openai",
            "warnings": plan.as_dict().get("warnings", []),
            "approved_plan": plan.as_dict(),
        }
        last_error = ""
        for attempt in range(3):
            try:
                generated = _generate_search_from_plan(prompt, plan, model, error_feedback=last_error)
            except OpportunitySearchError as exc:
                last_error = (
                    f"{exc} Return only the required JSON object with title, criteria_summary, assumptions, sql, and params. "
                    "Do not include markdown, prose, or comments outside JSON."
                )
                if attempt == 2:
                    raise
                continue
            try:
                result_rows = _run_generated_search(prompt, generated)
                if not result_rows and attempt < 2:
                    last_error = (
                        "The query returned zero parcel rows after app filters. Broaden conservatively while preserving the user's core asset intent. "
                        "Do not require zoning text to contain senior/adult/community unless the user explicitly says only such zones; use zoning suitability as score or match_reasons instead."
                    )
                    continue
                break
            except OpportunitySearchError as exc:
                last_error = str(exc)
                if attempt == 2:
                    raise
        result_diagnostics = _diagnose_results(prompt, plan, result_rows)
    except Exception as exc:
        fallback = _fallback_generated_search(prompt)
        if fallback:
            try:
                generated = fallback
                result_rows = _run_generated_search(prompt, generated)
                result_diagnostics = _diagnose_results(prompt, plan, result_rows)
            except Exception:
                pass
        if not generated or not result_rows:
            if generated:
                search.generated_sql = _strip_sql(generated.sql)
                search.generated_params = _json_safe(generated.params)
                search.title = generated.title[:220] or "AI opportunity search"
                search.criteria_summary = generated.criteria_summary[:1600]
                search.assumptions = _merged_assumptions(prompt, generated.assumptions)[:8]
                search.search_plan = _json_safe(plan.as_dict())
                search.plan_review = _json_safe(plan_review)
                search.result_diagnostics = _json_safe(result_diagnostics)
                search.save(
                    update_fields=[
                        "generated_sql",
                        "generated_params",
                        "title",
                        "criteria_summary",
                        "assumptions",
                        "search_plan",
                        "plan_review",
                        "result_diagnostics",
                        "updated_at",
                    ]
                )
            return _mark_error(search, _friendly_error(exc), model)

    search.title = generated.title[:220] or "AI opportunity search"
    search.criteria_summary = generated.criteria_summary[:1600]
    search.assumptions = _merged_assumptions(prompt, generated.assumptions)[:8]
    search.search_plan = _json_safe(plan.as_dict())
    search.plan_review = _json_safe(plan_review)
    search.result_diagnostics = _json_safe(result_diagnostics)
    search.generated_sql = _strip_sql(generated.sql)
    search.generated_params = _json_safe(generated.params)
    search.model = model
    search.result_rows = _json_safe(result_rows)
    search.result_count = len(result_rows)
    search.status = OpportunitySearch.STATUS_READY
    search.error = ""
    search.save(
        update_fields=[
            "title",
            "criteria_summary",
            "assumptions",
            "search_plan",
            "plan_review",
            "result_diagnostics",
            "generated_sql",
            "generated_params",
            "model",
            "result_rows",
            "result_count",
            "status",
            "error",
            "updated_at",
        ]
    )
    return search


def refresh_opportunity_search(search: OpportunitySearch) -> OpportunitySearch:
    return run_ai_opportunity_search(search.user, search.prompt, search=search)


def _run_generated_search(prompt: str, generated: GeneratedSearch) -> list[dict[str, Any]]:
    validate_search_sql(generated.sql, generated.params)
    explain_search_sql(generated.sql, generated.params)
    raw_rows = execute_search_sql(generated.sql, generated.params, DEFAULT_RESULT_LIMIT)
    return apply_prompt_result_filters(prompt, hydrate_result_rows(raw_rows))


def saved_searches_for_user(user, limit: int | None = None):
    qs = OpportunitySearch.objects.filter(user=user, saved_at__isnull=False).order_by("-saved_at", "-updated_at")
    return qs[:limit] if limit else qs


def recent_searches_for_user(user, limit: int | None = None):
    qs = OpportunitySearch.objects.filter(user=user).order_by("-updated_at", "-created_at")
    return qs[:limit] if limit else qs


def display_rows_for_search(search: OpportunitySearch, user) -> list[dict[str, Any]]:
    rows = copy.deepcopy(search.result_rows or [])
    rows = apply_prompt_result_filters(search.prompt, rows)
    return mark_saved(rows, user)


def apply_prompt_result_filters(prompt: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if _requires_bare_recreation_land(prompt):
        rows = [row for row in rows if _has_bare_recreation_land_evidence(row)]
    if _requires_dwelling_asset(prompt):
        rows = [row for row in rows if _has_dwelling_evidence(row)]
    return rows


def record_search_feedback(
    *,
    user,
    search: OpportunitySearch,
    rating: str,
    reason_code: str = "",
    comment: str = "",
    parcel_number: str = "",
) -> OpportunitySearchFeedback:
    if search.user_id != user.id:
        raise OpportunitySearchError("This search does not belong to the current user.")

    rating = (rating or "").strip().lower()
    reason_code = (reason_code or "").strip()
    parcel_number = (parcel_number or "").strip().upper()
    valid_ratings = {choice[0] for choice in OpportunitySearchFeedback.RATING_CHOICES}
    valid_reasons = {choice[0] for choice in OpportunitySearchFeedback.REASON_CHOICES}
    if rating not in valid_ratings:
        raise OpportunitySearchError("Choose thumbs up or thumbs down feedback.")
    if reason_code and reason_code not in valid_reasons:
        raise OpportunitySearchError("Choose a valid feedback reason.")

    feedback, _ = OpportunitySearchFeedback.objects.update_or_create(
        user=user,
        search=search,
        parcel_number=parcel_number,
        defaults={
            "rating": rating,
            "reason_code": reason_code,
            "comment": comment[:1000],
        },
    )
    return feedback


def validate_search_sql(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> str:
    stripped = _strip_sql(sql)
    if not stripped:
        raise OpportunitySearchError("The generated SQL was empty.")
    if ";" in stripped:
        raise OpportunitySearchError("Only one SQL statement is allowed.")
    if not re.match(r"(?is)^(select|with)\b", stripped):
        raise OpportunitySearchError("Only read-only SELECT/WITH queries are allowed.")
    if FORBIDDEN_SQL.search(stripped):
        raise OpportunitySearchError("The generated SQL used a forbidden operation.")
    if not re.search(r"(?i)\bparcel_number\b", stripped):
        raise OpportunitySearchError("The query must return a parcel_number column.")
    if re.search(r"(?is)\bs(?:ales)?\.sale_date_iso\s*(?:[<>]=?|=)\s*(?:current_date|now\(\)|date\b|timestamp\b|%s|\()", stripped):
        raise OpportunitySearchError("sales.sale_date_iso is text; date filters must guard and cast it with NULLIF(s.sale_date_iso, '')::date.")

    params = list(params or [])
    if re.search(r"(?<!%)%s[A-Za-z0-9_]", stripped) or re.search(r"(?<!%)%[A-Za-rt-zA-RT-Z]", stripped):
        raise OpportunitySearchError("SQL wildcard patterns must be passed as params, for example ILIKE %s with params ['%term%'].")
    placeholders = len(re.findall(r"(?<!%)%s(?![A-Za-z0-9_])", stripped))
    if placeholders != len(params):
        raise OpportunitySearchError("SQL placeholders and params did not match.")
    for value in params:
        if not _safe_param(value):
            raise OpportunitySearchError("SQL params must be simple JSON-compatible values.")

    ctes = _cte_names(stripped)
    for table in _referenced_tables(stripped):
        if table not in ALLOWED_TABLES and table not in ctes:
            raise OpportunitySearchError(f"Table {table} is not allowed for opportunity search.")
    return stripped


def execute_search_sql(sql: str, params: list[Any] | tuple[Any, ...] | None = None, limit: int = DEFAULT_RESULT_LIMIT) -> list[dict[str, Any]]:
    stripped = validate_search_sql(sql, list(params or []))
    wrapped = f"SELECT * FROM ({stripped}) opportunity_ai_search LIMIT %s"
    try:
        with connection.cursor() as cursor:
            cursor.execute(wrapped, [*(params or []), limit])
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError as exc:
        raise OpportunitySearchError(_database_error_message(exc)) from exc
    if "parcel_number" not in columns:
        raise OpportunitySearchError("The query result did not include parcel_number.")
    return rows


def explain_search_sql(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
    stripped = validate_search_sql(sql, list(params or []))
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN SELECT * FROM ({stripped}) opportunity_ai_search LIMIT 1", list(params or []))
    except DatabaseError as exc:
        raise OpportunitySearchError(_database_error_message(exc)) from exc


def hydrate_result_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parcel_numbers = []
    raw_by_parcel: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        parcel_number = str(row.get("parcel_number") or "").strip().upper()
        if not parcel_number or parcel_number in raw_by_parcel:
            continue
        parcel_numbers.append(parcel_number)
        raw_by_parcel[parcel_number] = row
    if not parcel_numbers:
        return []

    base_rows = _fetch(
        """
        SELECT p.parcel_number,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.owner_name, p.acres, z.zone_id, z.zone_name,
               z.waza_general, z.waza_specific, z.reference_url,
               p.assessed_value, p.impr_land_value, p.unimpr_land_value, p.building_value,
               p.land_use, p.utilities,
               split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code,
               ST_Y(ST_Centroid(g.geometry)) AS lat, ST_X(ST_Centroid(g.geometry)) AS lng
        FROM skagit_parcels p
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        WHERE p.parcel_number = ANY(%s)
          AND p.inactive_date IS NULL
        """,
        [parcel_numbers],
    )
    base_by_parcel = {str(row.get("parcel_number")).upper(): row for row in base_rows}
    hydrated = []
    for parcel_number in parcel_numbers:
        base = base_by_parcel.get(parcel_number)
        if base:
            item = _format_ai_result_row(base, raw_by_parcel[parcel_number])
        else:
            item = _fallback_result_row(parcel_number, raw_by_parcel[parcel_number])
        hydrated.append(item)
    return hydrated


def _format_ai_result_row(base: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    item = _base_row(base, "AI Search")
    reasons = _reason_labels(raw.get("match_reasons"))
    item["score"] = int(_coerce_number(raw.get("score")) or 0)
    item["signal_labels"] = reasons[:4] or feature_labels(base)
    item["ai_match_reasons"] = reasons
    item["source_tab"] = "ai-search"
    item["source_tab_label"] = "AI Search"
    item["why_it_ranks"] = "; ".join(reasons[:3]) if reasons else "Matched the natural-language search."
    item["risk_flags"] = risk_flags(
        "No parcel geometry" if not item["map_url"] else None,
        "Unknown zoning" if not base.get("zone_id") else None,
        "Natural resource zoning" if is_natural_resource_zone(base.get("zone_id"), base.get("zone_name"), base.get("waza_general")) else None,
        "Public/open-space zoning" if is_public_or_open_space_zone(base.get("waza_general")) else None,
        "Public/civic or moorage use" if is_public_or_civic_land_use(base.get("land_use")) else None,
        "Resource land" if is_resource_land_use(base.get("land_use")) else None,
        "No utility signal" if not utility_labels(base.get("utilities")) else None,
    )
    return item


def _fallback_result_row(parcel_number: str, raw: dict[str, Any]) -> dict[str, Any]:
    reasons = _reason_labels(raw.get("match_reasons"))
    return {
        "parcel_number": parcel_number,
        "location": "Parcel details unavailable",
        "city": "",
        "owner": "",
        "acres": None,
        "acres_fmt": "unknown acres",
        "land_use": "",
        "land_use_code": "",
        "current_use": "Unknown use",
        "utilities": "",
        "feature_labels": [],
        "signal_labels": reasons[:4],
        "past_due_years": [],
        "zoning": "Unknown zoning",
        "zone_name": "",
        "waza_general": "",
        "zone_definition": "",
        "zone_url": "",
        "assessed_value": None,
        "assessed_value_fmt": "$0",
        "land_value_fmt": "$0",
        "building_value_fmt": "$0",
        "score": int(_coerce_number(raw.get("score")) or 0),
        "risk_flags": ["Parcel not found in active assessor table"],
        "map_url": "",
        "parcel_url": "",
        "source_tab": "ai-search",
        "source_tab_label": "AI Search",
        "ai_match_reasons": reasons,
        "why_it_ranks": "; ".join(reasons[:3]) if reasons else "Matched the natural-language search.",
    }


def _generate_search_plan(prompt: str, model: str) -> SearchPlan:
    response = _openai_client().responses.create(
        model=model,
        input=_build_plan_prompt(prompt),
        temperature=0.1,
        max_output_tokens=1400,
    )
    return _search_plan_from_payload(_parse_json_object(_response_text(response)))


def _review_search_plan(prompt: str, plan: SearchPlan, model: str) -> SearchPlan:
    response = _openai_client().responses.create(
        model=model,
        input=_build_plan_review_prompt(prompt, plan),
        temperature=0.05,
        max_output_tokens=1600,
    )
    return _search_plan_from_payload(_parse_json_object(_response_text(response)))


def _generate_search_from_plan(prompt: str, plan: SearchPlan, model: str, error_feedback: str = "") -> GeneratedSearch:
    response = _openai_client().responses.create(
        model=model,
        input=_build_generation_prompt(prompt, plan=plan, error_feedback=error_feedback),
        temperature=0.1,
        max_output_tokens=2200,
    )
    payload = parse_generated_search_response(_response_text(response))
    return GeneratedSearch(
        title=str(payload.get("title") or "AI opportunity search"),
        criteria_summary=str(payload.get("criteria_summary") or ""),
        assumptions=[str(item)[:240] for item in _as_list(payload.get("assumptions"))],
        sql=str(payload.get("sql") or ""),
        params=_as_list(payload.get("params")),
    )


def _search_plan_from_payload(payload: dict[str, Any]) -> SearchPlan:
    return SearchPlan(
        title=str(payload.get("title") or "AI opportunity search")[:220],
        criteria_summary=str(payload.get("criteria_summary") or "")[:1600],
        asset_intent=str(payload.get("asset_intent") or "unspecified parcel opportunity")[:240],
        location=payload.get("location") if isinstance(payload.get("location"), dict) else {},
        hard_filters=_string_list(payload.get("hard_filters")),
        soft_rankers=_string_list(payload.get("soft_rankers")),
        exclusions=_string_list(payload.get("exclusions")),
        assumptions=_string_list(payload.get("assumptions")),
        relaxation_order=_string_list(payload.get("relaxation_order")),
        needs_zoning_definitions=bool(payload.get("needs_zoning_definitions")),
    )


def parse_generated_search_response(text: str) -> dict[str, Any]:
    parsed = _parse_json_object(text)
    required = {"title", "criteria_summary", "assumptions", "sql", "params"}
    missing = sorted(required - set(parsed))
    if missing:
        raise OpportunitySearchError(f"The AI response was missing: {', '.join(missing)}.")
    if not isinstance(parsed.get("assumptions"), list) or not isinstance(parsed.get("params"), list):
        raise OpportunitySearchError("AI assumptions and params must be arrays.")
    return parsed


def _parse_json_object(text: str) -> dict[str, Any]:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.strip("`").strip()
        if body.lower().startswith("json"):
            body = body[4:].strip()
    start = body.find("{")
    end = body.rfind("}")
    if start >= 0 and end > start:
        body = body[start : end + 1]
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpportunitySearchError("The AI response was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise OpportunitySearchError("The AI response must be a JSON object.")
    return parsed


def _fallback_generated_search(prompt: str) -> GeneratedSearch | None:
    if _requires_multiunit_asset(prompt):
        return _fallback_multiunit_search(prompt)
    if not _requires_dwelling_asset(prompt):
        return None
    place = _extract_place_hint(prompt)
    large_threshold = 2000 if "large" in _tokens(prompt) else 0
    where = [
        "p.inactive_date IS NULL",
        """(
            split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)
            OR dwelling.improvement_count > 0
        )""",
    ]
    params: list[Any] = [list(RESIDENTIAL_DWELLING_CODES)]
    if place:
        where.append(
            """(
                p.situs_city_state_zip ILIKE %s
                OR g.citydistrict ILIKE %s
                OR z.citydistrict ILIKE %s
                OR z.jurisdiction ILIKE %s
                OR p.city_district ILIKE %s
            )"""
        )
        pattern = f"%{place}%"
        params.extend([pattern, pattern, pattern, pattern, pattern])
    if large_threshold:
        where.append("COALESCE(p.living_area, dwelling.primary_living_area, 0) >= %s")
        params.append(large_threshold)

    sql = f"""
        SELECT
            p.parcel_number,
            (
                COALESCE(p.living_area, dwelling.primary_living_area, 0)
                + COALESCE(p.acres, 0) * 25
                + CASE WHEN z.zone_id IS NOT NULL THEN 50 ELSE 0 END
            ) AS score,
            array_remove(ARRAY[
                'residential dwelling evidence',
                CASE WHEN COALESCE(p.living_area, dwelling.primary_living_area, 0) >= 2000 THEN 'large living area' END,
                CASE WHEN %s <> '' THEN 'matched requested place' END,
                CASE WHEN z.zone_id IS NOT NULL THEN CONCAT(z.zone_id, ' zoning') END
            ], NULL) AS match_reasons
        FROM skagit_parcels p
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS improvement_count,
                   MAX(living_area_num) AS primary_living_area
            FROM improvements i
            WHERE i.parcelnumber = p.parcel_number
              AND i.imprv_det_type_cd IN ('MA','MA2','MA1.5F','UF2','UF1.5F','BMF','BMU','BMG')
        ) dwelling ON true
        WHERE {" AND ".join(where)}
        ORDER BY score DESC NULLS LAST
        LIMIT 100
    """
    params = [place or "", *params]
    place_phrase = f" in {place.title()}" if place else ""
    threshold_phrase = " over about 2,000 sq ft" if large_threshold else ""
    return GeneratedSearch(
        title=f"Residential dwelling candidates{place_phrase}",
        criteria_summary=(
            f"Residential parcels{place_phrase}{threshold_phrase}, ranked by living area, acreage, and zoning presence. "
            "Used because the AI-generated query could not produce a valid non-empty result."
        ),
        assumptions=[
            "Homes/houses require residential land-use or main dwelling improvement evidence.",
            "Senior/community conversion is treated as a suitability screen, not a hard zoning text filter.",
            "Results are screening leads only, not use or permit determinations.",
        ],
        sql=sql,
        params=params,
    )


def _fallback_multiunit_search(prompt: str) -> GeneratedSearch:
    years = _extract_years_hint(prompt) or 15
    wants_average = bool(_tokens(prompt) & AVERAGE_QUALITY_TERMS)
    quality_filter = ""
    if wants_average:
        quality_filter = """
          AND multi.average_quality_count > 0
        """
    sql = f"""
        SELECT
            p.parcel_number,
            (
                COALESCE(multi.unit_signal_count, 0) * 80
                + COALESCE(multi.average_quality_count, 0) * 25
                + COALESCE(p.acres, 0) * 5
            ) AS score,
            array_remove(ARRAY[
                'multi-unit building evidence',
                CASE WHEN multi.average_quality_count > 0 THEN 'average quality improvement signal' END,
                CASE WHEN NOT recent_sale.has_recent_sale THEN 'no sale in requested period' END
            ], NULL) AS match_reasons
        FROM skagit_parcels p
        LEFT JOIN assessor_rollup ar ON ar.parcel_number = p.parcel_number
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (
                    WHERE upper(COALESCE(i.imprv_det_type_description, '')) ~ '(DUPLEX|TRIPLEX|FOURPLEX|APARTMENT|MULTI)'
                       OR upper(COALESCE(i.imprv_det_class_description, '')) ~ '(DUPLEX|TRIPLEX|FOURPLEX|MULTI)'
                       OR upper(COALESCE(i.imprv_det_type_cd, '')) IN ('APT', 'DUP', 'TRI')
                ) AS unit_signal_count,
                COUNT(*) FILTER (
                    WHERE upper(COALESCE(i.imprv_det_class_cd, '')) IN ('MSA', '4', 'AVG')
                       OR upper(COALESCE(i.imprv_det_class_description, '')) ~ 'AVERAGE'
                       OR upper(COALESCE(i.condition_description, '')) = 'AVERAGE'
                ) AS average_quality_count
            FROM improvements i
            WHERE i.parcelnumber = p.parcel_number
        ) multi ON true
        LEFT JOIN LATERAL (
            SELECT EXISTS (
                SELECT 1
                FROM sales s
                WHERE s.parcel_number = p.parcel_number
                  AND s.sale_date_iso ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
                  AND NULLIF(s.sale_date_iso, '')::date >= CURRENT_DATE - (%s || ' years')::interval
            ) AS has_recent_sale
        ) recent_sale ON true
        WHERE p.inactive_date IS NULL
          AND (
            split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) IN ('113', '120', '130')
            OR upper(COALESCE(p.land_use, '')) ~ '(2-4 UNIT|5\\+ UNIT)'
            OR upper(COALESCE(ar.land_use_description, '')) ~ '(2-4 UNIT|5\\+ UNIT)'
          )
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) NOT IN (
            '0', '140', '150', '160', '450', '480', '670', '680', '710', '720', '730', '740', '750', '760', '770', '790',
            '810', '820', '830', '840', '850', '860', '880', '890', '920', '930', '940', '941', '970'
          )
          AND NOT recent_sale.has_recent_sale
          {quality_filter}
        ORDER BY score DESC NULLS LAST, p.assessed_value ASC NULLS LAST
        LIMIT 100
    """
    return GeneratedSearch(
        title="Multi-unit building candidates with no recent sales",
        criteria_summary=f"Parcels with duplex-to-sixplex or other multi-unit signals, no recorded sale in about {years} years, and average-quality signals when requested.",
        assumptions=[
            "Multi-unit evidence uses assessor land-use descriptions and improvement descriptions/classes.",
            "No recent sale uses sales.sale_date_iso after validating and casting the stored text date.",
            "Average quality uses assessor class/condition descriptions as a screening signal.",
        ],
        sql=sql,
        params=[years],
    )


def _fallback_search_plan(prompt: str) -> SearchPlan:
    place = _extract_place_hint(prompt)
    residential = _requires_dwelling_asset(prompt)
    hard_filters = ["active parcel"]
    exclusions = []
    if residential:
        hard_filters.append("residential dwelling evidence")
        exclusions.extend(["retail/service/government/industrial/resource-only parcels without dwelling evidence"])
    if place:
        hard_filters.append(f"place match: {place}")
    return SearchPlan(
        title="AI opportunity search",
        criteria_summary="Interprets the prompt into parcel asset, location, hard filters, ranking signals, exclusions, and relaxation order before SQL generation.",
        asset_intent="existing residential dwelling" if residential else "parcel opportunity",
        location={"place": place, "match_strategy": "situs/GIS/zoning place fields"} if place else {},
        hard_filters=hard_filters,
        soft_rankers=["larger building/lot signals", "zoning compatibility", "higher assessed or building value"],
        exclusions=exclusions,
        assumptions=["Screening signals are approximate and do not determine legal use or permit feasibility."],
        relaxation_order=["specific zoning language", "size threshold", "exact place match"],
        needs_zoning_definitions=True,
    )


def _diagnose_results(prompt: str, plan: SearchPlan, rows: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "row_count": len(rows),
        "asset_intent": plan.asset_intent,
        "warnings": [],
        "checks": [],
    }
    if not rows:
        diagnostics["warnings"].append("No rows matched after validation and app-level filters.")
        diagnostics["checks"].append("Try relaxing the lowest-priority items in relaxation_order.")
        return diagnostics

    if _requires_dwelling_asset(prompt):
        non_dwelling = [row.get("parcel_number") for row in rows if not _has_dwelling_evidence(row)]
        diagnostics["checks"].append("Residential dwelling evidence enforced.")
        if non_dwelling:
            diagnostics["warnings"].append(f"{len(non_dwelling)} rows lacked dwelling evidence after hydration.")
    natural_resource = [row.get("parcel_number") for row in rows if "Natural resource zoning" in (row.get("risk_flags") or [])]
    no_utilities = [row.get("parcel_number") for row in rows if "No utility signal" in (row.get("risk_flags") or [])]
    if natural_resource:
        diagnostics["warnings"].append(f"{len(natural_resource)} rows have natural-resource zoning; treat conversion suitability cautiously.")
    if no_utilities:
        diagnostics["warnings"].append(f"{len(no_utilities)} rows have no utility signal.")
    diagnostics["top_result_parcels"] = [row.get("parcel_number") for row in rows[:5]]
    return diagnostics


def _build_plan_prompt(prompt: str) -> str:
    return f"""
You are the planning stage for OpenSkagit Parcel Book natural-language opportunity search.
Do not write SQL. Convert the user request into a structured search plan.

Return only JSON with keys:
title, criteria_summary, asset_intent, location, hard_filters, soft_rankers, exclusions, assumptions, relaxation_order, needs_zoning_definitions.

Planning rules:
- Preserve the user's noun. If they ask for homes, houses, dwellings, residences, or residential buildings, asset_intent must be an existing residential dwelling, not merely a commercial parcel in compatible zoning.
- Split hard filters from soft rankers. Suitability words like suitable, potential, conversion, redevelopment, senior community, or adult community are usually rankers unless the user says must/only/required.
- Exclusions should name obvious wrong-result classes.
- Include a relaxation_order for zero-result handling.
- Location should identify place text and a match_strategy using situs/GIS/zoning place fields.

Schema and domain context:
{SCHEMA_CONTEXT}

Skill-backed data dictionary context:
{_skill_reference_context()}

Zoning MCP advisory context:
{_zoning_mcp_context(prompt)}

Prompt-specific deterministic hints:
{_intent_context(prompt)}

User prompt:
{prompt}
""".strip()


def _build_plan_review_prompt(prompt: str, plan: SearchPlan) -> str:
    return f"""
You are the critique stage for OpenSkagit Parcel Book AI search.
Review and repair this search plan before SQL generation. Return a complete corrected plan as JSON with the same keys.

Critique checklist:
- Does asset_intent preserve the user's noun?
- Are hard_filters truly mandatory?
- Are zoning/use-code suitability signals rankers unless the prompt explicitly requires them?
- Are wrong asset classes excluded?
- Is there a sensible relaxation_order for zero rows?
- Is location matching robust for unincorporated places?

User prompt:
{prompt}

Draft plan JSON:
{json.dumps(plan.as_dict(), default=str)}

Zoning MCP advisory context:
{_zoning_mcp_context(prompt, plan)}
""".strip()


def _build_generation_prompt(prompt: str, plan: SearchPlan, error_feedback: str = "") -> str:
    retry_note = ""
    if error_feedback:
        retry_note = (
            "\n\nThe previous SQL failed validation. Generate a corrected query. "
            f"Validation error: {error_feedback}"
        )
    return f"""
You are writing a safe PostgreSQL/PostGIS SELECT query for the OpenSkagit Parcel Book opportunity search.
Return only one compact JSON object with keys:
title, criteria_summary, assumptions, sql, params.

Rules:
- The user's prompt is arbitrary; do not hard-code examples or assume a fixed opportunity type.
- SQL must be one SELECT or WITH statement, no semicolons, no mutations, no temp objects.
- Use %s placeholders for user-provided values and put those values in params.
- For LIKE/ILIKE patterns, never write SQL string literals such as '%senior%' because %s inside words breaks DB params. Use ILIKE %s with params like ['%senior%'].
- Always return parcel_number. Optional useful columns are score and match_reasons.
- For match_reasons, use ARRAY['reason one', 'reason two'] or array_remove(ARRAY[CASE WHEN ... THEN 'reason' END], NULL). Do not use FILTER on ARRAY expressions.
- Keep result queries parcel-focused and cap expensive work before broad joins when possible.
- Prefer skagit_parcels p for current parcel facts and active parcels: p.inactive_date IS NULL.
- Join GIS and primary zoning as:
  LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
  LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
- Use assessor_rollup for readable land_use_description, utilities_description, and neighborhood_description when helpful.
- Utilities tokens include PWR, PWR-U, SEP, SEW, WTR-P, WTR-W, NONE.
- skagit_parcels.land_use often looks like '(911) UNDEVELOPED LAND INCORPORATED'; parse the code with split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1).
- sales.sale_date_iso is text, not a date column. Never compare s.sale_date_iso directly to CURRENT_DATE, DATE, timestamp, or interval expressions. Use a guarded cast such as s.sale_date_iso ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$' AND NULLIF(s.sale_date_iso, '')::date >= CURRENT_DATE - INTERVAL '5 years'.
- For no-home or vacant-like intent, use conservative screening signals such as low/zero p.building_value and/or NOT EXISTS main dwelling improvements.
- For bare land, raw land, undeveloped land, recreation land, camp/camping land, or small recreational parcel intent, exclude MH LEASED PROPERTY, leased manufactured-home land, condos, condominium/common-area parcels, public/civic/government/school/church/cemetery parcels, public open-space zoning, zero-acre/no-geometry records, and parcels with residential dwelling evidence.
- MH LEASED PROPERTY means leased manufactured homes are present on land that may not show normal MA dwelling improvements; do not treat it as bare land.
- Separate asset intent from zoning suitability. If the user asks for homes, houses, dwellings, residences, or residential buildings, the parcel must have residential dwelling evidence first; compatible commercial/mixed zoning alone is not enough.
- Residential dwelling evidence usually means land-use code in 110, 111, 112, 113, 120, 130, 180, 181, 182, 185, or 190, or a main dwelling improvement such as MA, MA2, MA1.5F, UF2, UF1.5F, BMF, BMU, or BMG.
- If the user asks for large homes/houses, do not return retail, restaurant, governmental, miscellaneous service, industrial, natural-resource, church, or personal-property parcels unless the prompt explicitly asks for those nonresidential conversions.
- Senior/adult community suitability can be a zoning or redevelopment screen, but it must not replace the requested asset type. Rank likely zoning after filtering for the requested parcel/building type.
- Words like suitable, potential, conversion, redevelopment, senior community, or adult community usually describe ranking/suitability signals. Do not make them mandatory zoning text filters unless the prompt explicitly says must be zoned for or only show allowed zones.
- For named place/location intent, match multiple place fields with ILIKE %s params: p.situs_city_state_zip, g.citydistrict, z.citydistrict, z.jurisdiction, and p.city_district. Do not rely on exact p.city_district; unincorporated places often appear only in situs_city_state_zip.
- For proximity intent, use PostGIS on gis_skagit_parcels.geometry. If a named city/place is requested, derive its comparison set from parcel data rather than assuming one city field is authoritative.
- Explain approximations in assumptions. Screening signals are not legal, permit, zoning, financing, or entitlement determinations.

Prompt-specific intent guidance:
{_intent_context(prompt)}

Approved search plan:
{json.dumps(plan.as_dict(), default=str)}

SQL generation rules from the approved plan:
- Every hard_filter must appear in WHERE unless it is impossible; impossible filters must be explained in assumptions.
- soft_rankers should affect score, ORDER BY, or match_reasons, not eliminate rows.
- exclusions should be implemented as WHERE exclusions where safe and schema-grounded.
- relaxation_order is for retry/zero-result behavior; do not over-filter on low-priority suitability text.

{SCHEMA_CONTEXT}

Skill-backed data dictionary context:
{_skill_reference_context()}

Zoning MCP advisory context:
{_zoning_mcp_context(prompt, plan)}

Allowed tables/views:
{", ".join(sorted(ALLOWED_TABLES))}

Core output shape example:
{{
  "title": "Large vacant parcels near a named place",
  "criteria_summary": "Parcels matching acreage, improvement, utility, and location signals from the prompt.",
  "assumptions": ["Vacant means low assessor building value unless the prompt says otherwise."],
  "sql": "SELECT p.parcel_number, 100 AS score, ARRAY['over acreage threshold'] AS match_reasons FROM skagit_parcels p WHERE p.inactive_date IS NULL AND p.acres > %s ORDER BY p.acres DESC",
  "params": [40]
}}

User prompt:
{prompt}
{retry_note}
""".strip()


@lru_cache(maxsize=1)
def _skill_reference_context() -> str:
    base = _skill_reference_dir()
    if not base:
        return FALLBACK_SKILL_REFERENCE_CONTEXT

    sections = [
        "OpenSkagit PostGIS skill reference excerpts. Use these to interpret user language, codes, and parcel facts; still obey the exact SQL schema above.",
    ]
    descriptions = _read_text(base / "descriptions.md")
    if descriptions:
        sections.append(_clip_text("Human-readable description guidance", descriptions, 5000))

    codes = _read_text(base / "codes.md")
    if codes:
        selected = "\n\n".join(
            part
            for part in [
                _extract_markdown_section(codes, "How To Use Codes"),
                _extract_markdown_section(codes, "Improvement Fields"),
                _extract_markdown_section(codes, "`land.land_type`"),
                _extract_markdown_section(codes, "`skagit_parcels.land_use`"),
                _extract_markdown_section(codes, "`utilities` Mappings"),
                _extract_markdown_section(codes, "`land_use` Mappings"),
            ]
            if part
        )
        if selected:
            sections.append(_clip_text("Assessor code and value guidance", selected, 9000))

    schema = _read_text(base / "schema.md")
    if schema:
        selected = "\n\n".join(
            part
            for part in [
                _extract_markdown_section(schema, "Core Relationships"),
                _extract_markdown_section(schema, "Core Tables"),
                _extract_markdown_section(schema, "Query Recipes"),
            ]
            if part
        )
        if selected:
            sections.append(_clip_text("Schema usage guidance", selected, 5000))

    context = "\n\n".join(sections).strip()
    max_chars = int(os.environ.get("OPPORTUNITY_SEARCH_SKILL_CONTEXT_CHARS", "18000"))
    return _clip_text("Skill reference context", context or FALLBACK_SKILL_REFERENCE_CONTEXT, max_chars)


def _zoning_mcp_context(prompt: str, plan: SearchPlan | None = None) -> str:
    if not _needs_zoning_mcp_context(prompt, plan):
        return "No zoning-specific advisory context requested for this prompt."
    plan_json = json.dumps(plan.as_dict(), sort_keys=True, default=str) if plan else ""
    return _cached_zoning_mcp_context((prompt or "").strip(), plan_json)


@lru_cache(maxsize=128)
def _cached_zoning_mcp_context(prompt: str, plan_json: str = "") -> str:
    try:
        from zoning_mcp import services as zoning_services
        from zoning_mcp.seed_data import JURISDICTIONS
    except Exception as exc:
        return f"Zoning MCP unavailable: {type(exc).__name__}. Continue with assessor/GIS zoning fields only."

    plan = _plan_from_json(plan_json)
    proposed_uses = _proposed_uses_for_zoning(prompt, plan)[:4]
    jurisdictions = _jurisdictions_for_zoning_context(prompt, plan, JURISDICTIONS)[:5]
    if not proposed_uses:
        return "No clear proposed land use was detected for zoning MCP lookup; use parcel zoning fields only as soft context."

    lines = [
        "Use this zoning_mcp context as advisory ranking/screening context, not as a legal determination.",
        "Do not replace requested asset type with zoning compatibility; filter for the requested parcel/building first.",
        f"Proposed use lookups: {', '.join(proposed_uses)}.",
        f"Jurisdiction focus: {', '.join(_jurisdiction_label(item, JURISDICTIONS) for item in jurisdictions)}.",
    ]

    for proposed_use in proposed_uses:
        try:
            comparison = zoning_services.compare_zones_for_use(proposed_use, jurisdictions=jurisdictions)
        except Exception as exc:
            lines.append(f"- {proposed_use}: zoning comparison unavailable ({type(exc).__name__}).")
            continue
        matches = [match for match in (comparison.get("matches") or []) if _zoning_match_relevant(proposed_use, match)]
        if not matches:
            lines.append(f"- {proposed_use}: no structured allowed-use matches found; treat zoning suitability as unknown.")
            continue
        compact_matches = []
        for match in matches[:10]:
            jurisdiction = _jurisdiction_label(match.get("jurisdiction"), JURISDICTIONS)
            zone = " ".join(str(part) for part in [match.get("zone_code"), match.get("zone_name")] if part).strip()
            status = match.get("status_label") or match.get("status") or "unknown"
            matched_use = match.get("matched_use") or proposed_use
            compact_matches.append(f"{jurisdiction} {zone}: {status} for {matched_use}")
        lines.append(f"- {proposed_use}: " + "; ".join(compact_matches))

    code_query = " ".join(proposed_uses[:3])
    for jurisdiction in jurisdictions[:3]:
        try:
            code_result = zoning_services.search_zoning_code(jurisdiction, code_query, limit=3)
        except Exception as exc:
            lines.append(f"- Source text for {_jurisdiction_label(jurisdiction, JURISDICTIONS)} unavailable ({type(exc).__name__}).")
            continue
        matches = code_result.get("matches") or []
        coverage = _zoning_coverage_label(code_result.get("coverage_status"))
        snippets = []
        for match in matches[:3]:
            title = str(match.get("title") or match.get("heading") or match.get("section") or "source").strip()
            snippet = str(match.get("snippet") or match.get("text") or "").strip()
            if snippet:
                snippet = re.sub(r"\s+", " ", snippet)[:260]
            snippets.append(f"{title}: {snippet}" if snippet else title)
        if snippets:
            lines.append(f"- Source text {_jurisdiction_label(jurisdiction, JURISDICTIONS)} ({coverage}): " + " | ".join(snippets))

    max_chars = int(os.environ.get("OPPORTUNITY_SEARCH_ZONING_CONTEXT_CHARS", "7000"))
    return _clip_text("Zoning MCP advisory context", "\n".join(lines), max_chars)


def _plan_from_json(plan_json: str) -> SearchPlan | None:
    if not plan_json:
        return None
    try:
        payload = json.loads(plan_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return _search_plan_from_payload(payload)


def _needs_zoning_mcp_context(prompt: str, plan: SearchPlan | None = None) -> bool:
    if plan and plan.needs_zoning_definitions:
        return True
    text = " ".join(
        [
            prompt or "",
            plan.asset_intent if plan else "",
            " ".join(plan.hard_filters if plan else []),
            " ".join(plan.soft_rankers if plan else []),
        ]
    )
    tokens = _tokens(text)
    return bool(tokens & ZONING_INTENT_TERMS)


def _proposed_uses_for_zoning(prompt: str, plan: SearchPlan | None = None) -> list[str]:
    text = " ".join(
        [
            prompt or "",
            plan.asset_intent if plan else "",
            plan.criteria_summary if plan else "",
        ]
    ).lower()
    tokens = _tokens(text.replace("-", " "))
    uses: list[str] = []

    def add(use: str) -> None:
        if use not in uses:
            uses.append(use)

    if tokens & {"senior", "seniors", "elder", "elderly", "assisted"}:
        add("senior housing")
        add("assisted living")
        add("residential care facility")
        add("adult family home")
    if _requires_multiunit_asset(text) or tokens & {"apartment", "apartments", "multifamily"}:
        add("multi-family dwelling")
        add("duplex")
        add("middle housing")
    if tokens & {"adu", "accessory"}:
        add("accessory dwelling unit")
    if tokens & {"camp", "camping", "campground"}:
        add("campground")
    if tokens & {"recreation", "recreational"}:
        add("recreational use")
    if tokens & {"restaurant", "restaurants", "cafe"}:
        add("restaurant")
    if tokens & {"retail", "shop", "commercial"}:
        add("small retail service business")
    if tokens & {"office", "professional"}:
        add("business professional office")
    if tokens & {"industrial", "warehouse"}:
        add("light industrial")
    if _requires_dwelling_asset(text):
        add("single family residence")

    if plan and plan.asset_intent and len(plan.asset_intent) <= 80:
        normalized_asset = plan.asset_intent.strip().lower()
        if normalized_asset and normalized_asset not in {"parcel", "parcels", "land"}:
            add(normalized_asset)
    return uses[:6]


def _jurisdictions_for_zoning_context(prompt: str, plan: SearchPlan | None, jurisdictions: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(part)
        for part in [
            prompt or "",
            (plan.location or {}).get("place") if plan else "",
            (plan.location or {}).get("jurisdiction") if plan else "",
        ]
        if part
    ).lower()
    aliases = {
        "skagit_county": ["skagit county", "county", "conway", "alger", "bow", "clear lake", "big lake"],
        "mount_vernon": ["mount vernon", "mt vernon"],
        "sedro_woolley": ["sedro woolley", "sedro-woolley", "sedro"],
        "burlington": ["burlington"],
        "anacortes": ["anacortes"],
        "concrete": ["concrete"],
        "la_conner": ["la conner", "laconner"],
    }
    found = [key for key, names in aliases.items() if key in jurisdictions and any(name in text for name in names)]
    if found:
        if "skagit_county" not in found:
            found.append("skagit_county")
        return found
    preferred = ["skagit_county", "sedro_woolley", "mount_vernon", "burlington", "anacortes", "concrete", "la_conner"]
    return [key for key in preferred if key in jurisdictions]


def _jurisdiction_label(jurisdiction: Any, jurisdictions: dict[str, Any]) -> str:
    key = str(jurisdiction or "").strip()
    configured = jurisdictions.get(key, {})
    return configured.get("display_name") or key.replace("_", " ").title() or "Unknown jurisdiction"


def _zoning_match_relevant(proposed_use: str, match: dict[str, Any]) -> bool:
    score = _coerce_number(match.get("match_score")) or 0
    if score >= 0.9:
        return True
    proposed_tokens = _meaningful_zoning_tokens(proposed_use)
    matched_tokens = _meaningful_zoning_tokens(match.get("matched_use") or match.get("normalized_use") or "")
    return bool(proposed_tokens and matched_tokens and proposed_tokens <= matched_tokens)


def _meaningful_zoning_tokens(value: Any) -> set[str]:
    stopwords = {"and", "or", "the", "a", "an", "use", "uses", "housing", "dwelling", "residence", "residential", "family", "home"}
    return {token for token in _tokens(str(value or "")) if token not in stopwords}


def _zoning_coverage_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("extraction_status") or value.get("status") or value.get("display_name") or "").strip()
    return str(value or "").strip()


def _skill_reference_dir() -> Path | None:
    configured = os.environ.get("OPENSKAGIT_POSTGIS_SKILL_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path.home() / ".codex" / "skills" / "openskagit-postgis")
    for candidate in candidates:
        references = candidate / "references"
        if references.exists():
            return references
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_markdown_section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"(?im)^(#+)\s+{re.escape(heading)}\s*$")
    match = pattern.search(markdown or "")
    if not match:
        return ""
    level = len(match.group(1))
    next_heading = re.search(rf"(?m)^#{{1,{level}}}\s+", markdown[match.end() :])
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.start() : end].strip()


def _clip_text(label: str, text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return f"{label}:\n{text}" if label else text
    return f"{label}:\n{text[:max_chars].rstrip()}\n[truncated]"


def _mark_error(search: OpportunitySearch, error: str, model: str = "") -> OpportunitySearch:
    search.status = OpportunitySearch.STATUS_ERROR
    search.error = error[:2000]
    search.model = model
    search.result_rows = []
    search.result_count = 0
    search.save(update_fields=["status", "error", "model", "result_rows", "result_count", "updated_at"])
    return search


def _search_model() -> str:
    return os.environ.get("OPPORTUNITY_SEARCH_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"


def _openai_client():
    from openai import OpenAI

    timeout = float(os.environ.get("OPPORTUNITY_SEARCH_TIMEOUT", "75"))
    return OpenAI(timeout=timeout)


def _strip_sql(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def _cte_names(sql: str) -> set[str]:
    if not re.match(r"(?is)^with\b", sql):
        return set()
    return {name.lower() for name in re.findall(r"(?is)(?:with|,)\s+([a-z_][a-z0-9_]*)\s+as\s*\(", sql)}


def _referenced_tables(sql: str) -> set[str]:
    tables = set()
    pattern = re.compile(r"(?is)\b(?:from|join)\s+(?!lateral\b)(?:only\s+)?(?:public\.)?([a-z_][a-z0-9_]*)")
    for match in pattern.finditer(sql):
        table = match.group(1).lower()
        if table not in {"select", "unnest", "jsonb_array_elements"}:
            tables.add(table)
    return tables


def _safe_param(value: Any) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list | tuple):
        return all(_safe_param(item) for item in value)
    return False


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


def _coerce_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    items = []
    for item in _as_list(value):
        if isinstance(item, dict):
            text = "; ".join(f"{key}={val}" for key, val in item.items())
        else:
            text = str(item)
        text = text.strip()
        if text:
            items.append(text[:240])
    return items


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    return str(response)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, OpportunitySearchError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def _merged_assumptions(prompt: str, assumptions: list[str]) -> list[str]:
    merged = [str(item) for item in assumptions if str(item).strip()]
    if _requires_dwelling_asset(prompt):
        merged.append("Because the prompt asks for homes or residential buildings, results are filtered to parcels with residential dwelling evidence; zoning suitability is treated as secondary.")
    if _requires_bare_recreation_land(prompt):
        merged.append("Because the prompt asks for bare/recreation land, results exclude leased manufactured-home, condo/common-area, public/civic/open-space, and existing dwelling parcels.")
    return merged


def _intent_context(prompt: str) -> str:
    lines = []
    if _requires_dwelling_asset(prompt):
        lines.append(
            "Detected residential dwelling asset intent. Require residential land_use_code or main dwelling improvements; exclude purely commercial/service/government/resource parcels unless explicitly requested."
        )
    if _requires_bare_recreation_land(prompt):
        lines.append(
            "Detected bare/recreation land intent. Exclude MH leased property, condominium/common-area parcels, public/civic/open-space parcels, zero-acre/no-geometry records, and parcels with residential dwelling evidence. Treat private vacant/undeveloped land as the core asset."
        )
    if _tokens(prompt) & {"senior", "seniors", "adult", "adults", "elder", "elderly", "assisted", "community", "communities"}:
        lines.append(
            "Detected senior/adult/community reuse intent. Consider zoning and larger building/lot signals, but do not let zoning override the requested existing asset type."
        )
    if not lines:
        lines.append("No extra deterministic intent rule detected; translate the prompt conservatively.")
    return "\n".join(f"- {line}" for line in lines)


def _requires_dwelling_asset(prompt: str) -> bool:
    tokens = _tokens(prompt)
    return bool(tokens & DWELLING_ASSET_TERMS) and not bool(tokens & EXPLICIT_NONRESIDENTIAL_TERMS)


def _requires_bare_recreation_land(prompt: str) -> bool:
    tokens = _tokens(prompt)
    has_land_intent = bool(tokens & LAND_ASSET_TERMS)
    has_bare_or_recreation_intent = bool(tokens & BARE_RECREATION_TERMS)
    return has_land_intent and has_bare_or_recreation_intent and not _requires_dwelling_asset(prompt)


def _requires_multiunit_asset(prompt: str) -> bool:
    normalized = (prompt or "").lower().replace("-", "")
    tokens = _tokens(normalized)
    return (
        bool(tokens & MULTIUNIT_TERMS)
        or "sixplex" in normalized
        or "fiveplex" in normalized
        or "fourplex" in normalized
        or "triplex" in normalized
        or "duplex" in normalized
        or "multi unit" in (prompt or "").lower()
    )


def _extract_years_hint(prompt: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\s+years?\b", (prompt or "").lower())
    if not match:
        return None
    years = int(match.group(1))
    return years if 1 <= years <= 50 else None


def _has_bare_recreation_land_evidence(row: dict[str, Any]) -> bool:
    code = str(row.get("land_use_code") or "").strip()
    text = " ".join(
        str(row.get(key) or "")
        for key in ("land_use", "current_use", "zoning", "zone_name", "waza_general")
    ).upper()
    if any(term in text for term in BAD_BARE_LAND_TEXT):
        return False
    if _has_dwelling_evidence(row):
        return False
    if is_public_or_civic_land_use(row.get("land_use")) or is_public_or_open_space_zone(row.get("waza_general")):
        return False
    if not row.get("map_url") and _coerce_number(row.get("acres")) in (None, 0):
        return False
    acres_value = _coerce_number(row.get("acres"))
    if acres_value is not None and acres_value <= 0:
        return False
    if code in {"0", "140", "150", "160", "500", "670", "680", "760", "930", "970"}:
        return False
    return True


def _has_dwelling_evidence(row: dict[str, Any]) -> bool:
    code = str(row.get("land_use_code") or "").strip()
    if code in RESIDENTIAL_DWELLING_CODES:
        return True
    use_text = f"{row.get('land_use') or ''} {row.get('current_use') or ''}".upper()
    if any(term in use_text for term in ("HOUSEHOLD", "SFR", "MANUFACTURED HOME", "VACATION", "CABIN", "DWELLING")):
        return True
    if code.startswith(NONRESIDENTIAL_LAND_USE_PREFIXES) or code == "0":
        return False
    return False


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _extract_place_hint(prompt: str) -> str:
    match = re.search(
        r"\b(?:in|near|around|close\s+to)\s+([a-z][a-z\s-]{1,40}?)(?:\s+(?:suitable|that|with|for|over|under|above|below|could|can|to|and)\b|$)",
        (prompt or "").lower(),
    )
    if not match:
        return ""
    place = re.sub(r"[^a-z\s-]", "", match.group(1)).strip(" -")
    words = [word for word in place.split() if word not in {"the", "a", "an"}]
    return " ".join(words[:4])


def _database_error_message(exc: DatabaseError) -> str:
    text = str(exc).strip().splitlines()[0]
    if "does not exist" in text and "column" in text:
        return f"The generated SQL referenced a column that does not exist: {text}"
    if "does not exist" in text and "relation" in text:
        return f"The generated SQL referenced a table or view that does not exist: {text}"
    return f"The generated SQL did not pass database validation: {text}"


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
