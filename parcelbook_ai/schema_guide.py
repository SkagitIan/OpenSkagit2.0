"""LLM-facing semantic guide for parcel_search.parquet."""

from __future__ import annotations

import os

DEFAULT_PARQUET_PATH = "r2://openskagit/derived/parcel_search.parquet"

FIELDS = [
    "parcel_number", "situs_address", "situs_city_state_zip", "owner_name", "land_use",
    "acres", "assessed_value", "has_geometry", "has_situs_address", "city_name",
    "inside_city_limits", "zoning_code_short", "zoning_label",
    "primary_building_living_area", "total_living_area", "improvement_building_count",
    "primary_actual_year_built", "last_valid_sale_date", "last_valid_sale_price",
    "years_since_last_valid_sale", "has_valid_sale", "sold_last_12_months", "sold_last_5_years",
]


def get_parcel_search_semantic_guide() -> str:
    path = os.environ.get("PARCEL_SEARCH_PARQUET_PATH", DEFAULT_PARQUET_PATH)
    return f"""
ParcelBook parcel_search semantic guide
- Table grain: parcel_search.parquet is one row per parcel_number.
- Source path: {path}
- Query source: use read_parquet('{path}') only.
- Important fields: {', '.join(FIELDS)}.
- Use acres for parcel size.
- Use assessed_value for assessed value; assessed value is not market value.
- Use primary_building_living_area for normal house-size reasoning.
- Use total_living_area only for total built area, multiple buildings, apartments, cabins, commercial, or multi-improvement properties.
- Use primary_actual_year_built for older/newer building searches.
- Use years_since_last_valid_sale for stale ownership / has not sold recently.
- Use city_name and inside_city_limits for city/incorporated-area context.
- Use zoning_code_short and zoning_label as parcel discovery signals only; do not use zoning_code_short or zoning_label as a legal determination.
- Missing geometry or situs address is a data gap, not proof the parcel is invalid.
- Do not answer zoning feasibility, allowed-use, development-standard, buildability, ADU, subdivision, density, setback, height, lot coverage, or parking questions from parcel_search.parquet alone. Use zoning_mcp when those issues matter.
""".strip()
