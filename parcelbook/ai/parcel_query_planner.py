"""Natural-language to DuckDB SQL planner for ParcelBook."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .prompts import PLANNER_SYSTEM_PROMPT, planner_user_prompt

SOURCE = "read_parquet('r2://openskagit/derived/parcel_search.parquet')"

@dataclass
class QueryPlan:
    intent: str
    plan: str
    sql: str
    caveats: list[str]


def plan_parcel_query(user_query: str, *, schema_text: str | None = None) -> QueryPlan:
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return _plan_with_openai(user_query, schema_text=schema_text)
        except Exception:
            # Keep the feature usable in dev/test; callers can log if desired.
            pass
    return heuristic_plan(user_query)


def _plan_with_openai(user_query: str, *, schema_text: str | None = None) -> QueryPlan:
    from openai import OpenAI
    client = OpenAI()
    model = os.environ.get("PARCELBOOK_QUERY_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": planner_user_prompt(user_query, schema_text)},
        ],
        temperature=0.2,
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return QueryPlan(
        intent=payload.get("intent", user_query),
        plan=payload.get("plan", "LLM-generated parcel search"),
        sql=payload["sql"],
        caveats=payload.get("caveats", []),
    )


def heuristic_plan(user_query: str) -> QueryPlan:
    q = user_query.lower()
    filters = ["1=1"]
    score = ["0"]
    intent = "Flexible parcel search"

    if "mount vernon" in q:
        filters.append("city_name ILIKE '%Mount Vernon%'")
    if "sedro" in q:
        filters.append("city_name ILIKE '%Sedro%'")
    if "burlington" in q:
        filters.append("city_name ILIKE '%Burlington%'")
    if "city" in q or "adu" in q:
        filters.append("inside_city_limits = TRUE")
        score.append("CASE WHEN inside_city_limits THEN 15 ELSE 0 END")
    if "rural" in q:
        filters.append("COALESCE(inside_city_limits, FALSE) = FALSE")
    if "residential" in q or "home" in q or "house" in q or "adu" in q:
        filters.append("COALESCE(land_use, '') ILIKE '%res%'")
    if "manufactured" in q or "mobile" in q:
        filters.append("(COALESCE(primary_building_style, '') ILIKE '%manufact%' OR COALESCE(improvement_descriptions, '') ILIKE '%manufact%' OR COALESCE(land_use, '') ILIKE '%mobile%')")
    if "no situs" in q:
        filters.append("has_situs_address = FALSE")
    elif "adu" in q:
        filters.append("has_situs_address = TRUE")
    if "valid geometry" in q or "adu" in q:
        filters.append("has_geometry = TRUE")
    if "missing geometry" in q:
        filters.append("has_geometry = FALSE")
    if "2 and 10 acres" in q:
        filters.append("acres BETWEEN 2 AND 10")
    elif "quarter acre" in q:
        filters.append("acres >= 0.25")
    elif "large" in q or "big lot" in q or "larger lot" in q or "adu" in q:
        filters.append("acres >= 0.25")
        score.append("CASE WHEN acres >= 1 THEN 15 WHEN acres >= 0.5 THEN 10 WHEN acres >= 0.25 THEN 5 ELSE 0 END")
    if "small" in q or "adu" in q:
        filters.append("primary_building_living_area BETWEEN 500 AND 3000")
        score.append("CASE WHEN primary_building_living_area <= 1400 THEN 15 ELSE 5 END")
    if "older" in q or "old" in q or "adu" in q:
        filters.append("primary_actual_year_built IS NOT NULL AND primary_actual_year_built <= 1985")
        score.append("CASE WHEN primary_actual_year_built <= 1960 THEN 15 WHEN primary_actual_year_built <= 1985 THEN 8 ELSE 0 END")
    if "no recent sale" in q or "not sold" in q or "forever" in q:
        filters.append("(years_since_last_valid_sale IS NULL OR years_since_last_valid_sale >= 10)")
        score.append("CASE WHEN years_since_last_valid_sale IS NULL THEN 8 WHEN years_since_last_valid_sale >= 15 THEN 12 ELSE 6 END")
    if "recently sold" in q or "recent sales" in q:
        filters.append("sold_last_5_years = TRUE")
    if "under $400k" in q or "under 400k" in q:
        filters.append("assessed_value < 400000")
    elif "moderate assessed" in q or "adu" in q:
        filters.append("assessed_value BETWEEN 250000 AND 900000")
    if "secondary" in q or "detached unit" in q:
        filters.append("improvement_building_count >= 2")
        score.append("CASE WHEN improvement_building_count >= 2 THEN 20 ELSE 0 END")
        intent = "Possible parcels with secondary detached improvement signals"
    if "adu" in q:
        filters.append("improvement_building_count <= 2")
        filters.append("(COALESCE(zoning_code_short, '') ILIKE '%RI%' OR COALESCE(zoning_code_short, '') ILIKE '%RR%' OR COALESCE(zoning_code_short, '') ILIKE '%CITY%')")
        intent = "Possible ADU candidate search"

    sql = f"""
SELECT
  parcel_number, situs_address, situs_city_state_zip, owner_name, land_use,
  acres, assessed_value, city_name, inside_city_limits, zoning_code_short, zoning_label,
  has_geometry, has_situs_address, primary_building_living_area, primary_actual_year_built,
  primary_building_age, improvement_building_count, primary_building_style,
  years_since_last_valid_sale, last_valid_sale_date, last_valid_sale_price,
  ({' + '.join(score)}) AS match_score
FROM {SOURCE}
WHERE {' AND '.join(filters)}
ORDER BY match_score DESC, acres DESC NULLS LAST, assessed_value ASC NULLS LAST
LIMIT 25
""".strip()
    return QueryPlan(
        intent=intent,
        plan="Heuristic fallback plan using city, land-use, size, building age, sale recency, and data-availability signals inferred from the prompt.",
        sql=sql,
        caveats=["Zoning/comprehensive-plan fields are signals and require code verification.", "Missing sale fields mean no valid sale summary was found.", "Primary building fields are summarized from improvement data."],
    )
