# ParcelBook Query Planner Skill

Use this reasoning guide when translating natural-language parcel questions into DuckDB SQL.

## Core behavior
- Treat `parcel_search.parquet` as the canonical user-facing table.
- It is one row per `parcel_number`; do not join raw sales or raw improvement detail rows.
- Infer intent, produce a short plan, generate safe SELECT SQL, then explain why results matched.
- Keep the experience flexible and AI-powered, not a fixed category dashboard.

## Data semantics
- `acres` is parcel size.
- `assessed_value` is current assessed value.
- `primary_building_living_area` is the best main-building house-size field for residential queries.
- `total_living_area` may include multiple buildings; only use it when total built area or multi-building context matters.
- `primary_actual_year_built` and `primary_building_age` come from summarized improvement records.
- `years_since_last_valid_sale` is a stale ownership / sale-recency signal.
- `city_name` and `inside_city_limits` come from city-limits GIS overlay.
- `zoning_code_short` and `zoning_label` are comprehensive-plan/GIS signals, not legal zoning determinations.
- `has_geometry` and `has_situs_address` are data-availability flags; missing values are expected for some parcels.

## Safety
- Use only `read_parquet('r2://openskagit/derived/parcel_search.parquet')`.
- Generate SELECT-only SQL with LIMIT.
- Do not use INSERT, UPDATE, DELETE, DROP, COPY, CREATE, ALTER, ATTACH, INSTALL, LOAD, PRAGMA, or SECRET.
- Do not invent fields.
