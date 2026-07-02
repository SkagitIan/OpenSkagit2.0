"""Parcel result explanation helpers."""

from __future__ import annotations

from typing import Any

DEFAULT_CAVEATS = [
    "Zoning/comprehensive-plan fields are GIS-derived signals and should be verified against the applicable code.",
    "Missing sale date/price means no valid sale summary was found for that parcel.",
    "Missing geometry means the parcel may not be mappable from the current GIS layer.",
    "Primary building fields are summarized from improvement records.",
]


def explain_rows(user_query: str, rows: list[dict[str, Any]], *, caveats: list[str] | None = None) -> list[dict[str, Any]]:
    explained = []
    for row in rows:
        reasons = []
        if row.get("city_name"):
            reasons.append(f"city/GIS context: {row['city_name']}")
        if row.get("acres") is not None:
            reasons.append(f"lot size: {row['acres']} acres")
        if row.get("primary_building_living_area") is not None:
            reasons.append(f"primary building size: {row['primary_building_living_area']} sf")
        if row.get("primary_actual_year_built") is not None:
            reasons.append(f"primary year built: {row['primary_actual_year_built']}")
        if row.get("years_since_last_valid_sale") is not None:
            reasons.append(f"last valid sale age: {row['years_since_last_valid_sale']} years")
        if row.get("improvement_building_count") is not None:
            reasons.append(f"improvement/building count: {row['improvement_building_count']}")
        if row.get("assessed_value") is not None:
            reasons.append(f"assessed value: ${row['assessed_value']:,.0f}")
        explained.append({**row, "match_explanation": "; ".join(reasons) or "Matched the generated SQL filters."})
    return explained


def standard_caveats(extra: list[str] | None = None) -> list[str]:
    return list(dict.fromkeys((extra or []) + DEFAULT_CAVEATS))
