"""Semantic notes for the R2/DuckDB parcel_search parcel layer."""

from __future__ import annotations


_FIELD_NOTES = [
    ("parcel_number", "Stable Skagit parcel identifier; use as the parcel_id for zoning tools."),
    ("situs_address", "Physical situs street address when available; missing values are data gaps."),
    ("situs_city_state_zip", "City/state/ZIP portion of the situs address when available."),
    ("city_name", "Municipal city name signal from parcel/GIS data; normalize before using as a jurisdiction."),
    ("inside_city_limits", "Boolean city-limits signal; false or null generally means use Skagit County unless better data exists."),
    ("zoning_code_short", "Short zoning-code signal from parcel search; verify against source zoning code before legal conclusions."),
    ("zoning_label", "Human-readable zoning label signal; not a final legal zoning determination."),
    ("has_geometry", "Whether geometry was present in the parcel-search build; false is a data gap, not proof of nonexistence."),
    ("has_situs_address", "Whether situs address fields were present; false is a data gap, not proof of no address."),
    ("acres", "Parcel acreage signal for rough context; verify for regulatory thresholds."),
    ("land_use", "Assessor/parcel land-use description; do not substitute for zoning use permissions."),
    ("assessed_value", "Assessed value for tax context; it is not market value."),
    ("primary_building_living_area", "Preferred house/building size signal for the primary building when available."),
    ("total_living_area", "Aggregate living-area signal; use cautiously and do not treat as the normal house-size field."),
    ("improvement_building_count", "Count of improvement buildings in assessor-derived data when available."),
    ("primary_actual_year_built", "Actual year built for the primary building when available."),
    ("years_since_last_valid_sale", "Recency signal for the last valid sale; missing values are data gaps."),
]


def get_parcel_search_semantic_guide() -> str:
    """Return concise LLM/tool guidance for parcel_search.parquet fields."""
    lines = [
        "parcel_search.parquet is a parcel discovery and facts layer, not legal zoning authority.",
        "Use it to resolve parcel_number, address, jurisdiction signals, zoning-code signals, and assessor facts; use zoning_mcp source-code tools for legal interpretation.",
        "Fields zoning_mcp uses:",
    ]
    lines.extend(f"- {name}: {description}" for name, description in _FIELD_NOTES)
    return "\n".join(lines)
