---
name: openskagit-postgis
description: Write SQL, answer schema and code-definition questions, capture human-readable data descriptions, and support coding tasks for the OpenSkagit-railway PostGIS database. Use when working on OpenSkagit parcel, assessor, improvement, land, utility, neighborhood-code, tax, levy, zoning, land-ledger, tax-delinquency, opportunity, or spatial queries; when explaining assessor codes such as MA, MSA, land-use codes, condition codes, utility tokens, zoning labels, or *_description fields; when building AI-to-SQL context or Django raw SQL for C:\Users\ian\Desktop\Factory\OpenSkagit-railway; or when a task needs knowledge of the OpenSkagit Postgres/PostGIS schema.
---

# OpenSkagit PostGIS

## Quick Start

Use this skill for OpenSkagit database work in `C:\Users\ian\Desktop\Factory\OpenSkagit-railway`.

Read `references/schema.md` before writing non-trivial SQL, answering schema questions, changing database-backed code, or explaining data relationships. For small tasks, skim the "Core Tables" and "Query Recipes" sections first.

Read `references/codes.md` when the task involves assessor code definitions, parcel improvement records, land-use descriptions, condition/quality classes, utility tokens, neighborhood codes, or questions like "what does MA mean?"

Read `references/descriptions.md` when the task is about making data human-readable, documenting field meanings, preserving raw code plus readable label pairs, improving AI-to-SQL context, or building opportunity queries that should return plain-English labels instead of cryptic assessor/GIS codes.

Prefer read-only SQL unless the user explicitly asks for a migration, import, rebuild, or data mutation. When writing mutating SQL, make the transaction boundary explicit and include a verification query.

## Connection

The Django app reads the database URL from `.env` in this order:

1. `NEW_DATABASE_URL`
2. `POSTGIS_DATABASE_URL`
3. `DATABASE_URL`

Use Django's configured connection for app tasks. Avoid copying secrets into responses or skill files.

For live introspection from the project root, use Python with `python-dotenv` and `psycopg`, or `python manage.py shell`. `psql` may not be installed on the machine.

## SQL Conventions

Use explicit table aliases and quote only when needed. Most OpenSkagit tables are lowercase snake_case in `public`.

Treat `parcel_number` and `parcel_id` as text identifiers. Join parcel tables like this:

```sql
FROM skagit_parcels p
LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
```

Filter active assessor parcels with:

```sql
WHERE p.inactive_date IS NULL
```

Use `ST_AsGeoJSON(geometry, 7)::json` for API payloads and `ST_Transform(..., 4326)` when normalizing spatial output. Geometry columns are already registered as SRID 4326 MultiPolygon in the live database.

For coded assessor fields, prefer existing normalized description columns when available, then fall back to `code_mappings`. In `improvements`, use `imprv_det_type_description`, `imprv_det_class_description`, and `condition_description`; if those are absent or stale, join `code_mappings` using categories `improvement_type`, `improvement_class`, and `condition`.

For human-facing results, preserve both the raw code and readable description. Prefer `assessor_rollup` for normalized description fields such as `land_use_description`, `neighborhood_description`, and `utilities_description`; prefer `skagit_parcels` for current production parcel/value/tax screens, then add readable labels from `assessor_rollup` or `code_mappings`.

## Verification

Before finalizing SQL, check that referenced columns exist in `references/schema.md` or by live introspection. For performance-sensitive queries, check available indexes and prefer indexed join/filter columns such as `skagit_parcels.parcel_number`, `skagit_parcels.levy_code`, `gis_skagit_parcels.parcel_id`, `parcel_primary_zoning.parcel_id`, `parcel_primary_zoning.zone_id`, and GiST geometry indexes.

If the answer depends on current row counts, rebuild status, fresh tax data, or rare code values not listed in the references, query the live database instead of relying only on the reference.
