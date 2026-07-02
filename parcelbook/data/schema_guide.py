"""Schema inspection and LLM-facing field guide for parcel_search.parquet."""

from __future__ import annotations

from dataclasses import dataclass

from .duckdb_r2 import DuckDBR2Client

FIELD_DESCRIPTIONS = {
    "parcel_number": "Stable parcel identifier; parcel_search is one row per parcel_number.",
    "acres": "Parcel size in acres.",
    "assessed_value": "Current assessor total assessed value.",
    "primary_building_living_area": "Best single main-building living area; prefer for normal house-size queries.",
    "total_living_area": "Summed living area across improvement buildings; use cautiously for multi-building or total built-area queries.",
    "primary_actual_year_built": "Best actual year built for the primary building.",
    "primary_building_age": "Current-year age of the primary building from improvement data.",
    "years_since_last_valid_sale": "Years since last valid deed-date sale; useful stale ownership / sale-recency signal.",
    "city_name": "Incorporated city name from GIS city-limits overlay when present.",
    "inside_city_limits": "True when parcel point is inside a city-limits GIS layer.",
    "zoning_code_short": "Comprehensive plan / zoning short code from GIS overlay; signal only, verify legal zoning.",
    "zoning_label": "Human-readable comprehensive plan / zoning label; signal only, verify legal zoning.",
    "land_use": "Broad assessor land-use classification.",
    "improvement_building_count": "Number of collapsed improvement/building records for the parcel.",
    "has_geometry": "True when GIS parcel point/geometry data exists; false is expected for some parcels.",
    "has_situs_address": "True when a situs address exists; false is expected for some parcels.",
    "has_valid_sale": "True when sales summary found at least one valid sale.",
    "sold_last_12_months": "True when latest valid sale is within the past 12 months.",
    "sold_last_5_years": "True when latest valid sale is within the past 5 years.",
    "primary_building_style": "Primary building style text from summarized improvements.",
    "improvement_descriptions": "Distinct improvement descriptions summarized at parcel level.",
}

@dataclass(frozen=True)
class SchemaColumn:
    name: str
    duckdb_type: str
    description: str = ""


def inspect_schema(client: DuckDBR2Client | None = None) -> list[SchemaColumn]:
    client = client or DuckDBR2Client()
    df = client.inspect_parcel_search_schema()
    return [
        SchemaColumn(
            name=str(row["column_name"]),
            duckdb_type=str(row["column_type"]),
            description=FIELD_DESCRIPTIONS.get(str(row["column_name"]), ""),
        )
        for _, row in df.iterrows()
    ]


def schema_guide(columns: list[SchemaColumn] | None = None) -> str:
    intro = [
        "parcel_search.parquet is one row per parcel_number.",
        "Use read_parquet('r2://openskagit/derived/parcel_search.parquet') as the only source.",
        "Do not drop parcels solely because has_geometry or has_situs_address is false unless the user asks for mappable/addressed results.",
        "Use primary_building_living_area for normal house-size queries; total_living_area can include multiple buildings and should be used cautiously.",
        "Zoning/comprehensive-plan fields are data signals and require code verification before legal conclusions.",
    ]
    if not columns:
        fields = [f"- {name}: {desc}" for name, desc in sorted(FIELD_DESCRIPTIONS.items())]
    else:
        fields = [
            f"- {col.name} ({col.duckdb_type})" + (f": {col.description}" if col.description else "")
            for col in columns
        ]
    return "\n".join(intro + ["", "Important fields:"] + fields)
