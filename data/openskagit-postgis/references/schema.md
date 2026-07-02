# OpenSkagit PostGIS Schema Reference

Snapshot source: live database configured by `C:\Users\ian\Desktop\Factory\OpenSkagit-railway\.env`, inspected on 2026-06-23. Do not store credentials here.

For assessor code definitions and examples, also read `codes.md`.

Extensions: `postgis`, `postgis_topology`, `plpgsql`.

Live catalog summary at inspection time: 58 non-system relations, 732 columns, 117 indexes, 4 registered geometry columns.

## Core Relationships

- Parcel identity: `skagit_parcels.parcel_number` is the main parcel key.
- GIS parcel join: `gis_skagit_parcels.parcel_id = skagit_parcels.parcel_number`.
- Primary zoning join: `parcel_primary_zoning.parcel_id = skagit_parcels.parcel_number`.
- Full zoning join: `parcel_zoning.parcel_id = skagit_parcels.parcel_number`.
- Tax detail joins by parcel: `v_parcel_tax_summary.parcel_number = skagit_parcels.parcel_number`; `v_parcel_tax_detail.parcel_number = skagit_parcels.parcel_number`.
- Levy composition joins by levy: `skagit_levy_composition.levy_code = skagit_parcels.levy_code`; use `tax_year` to disambiguate.
- Levy crosswalk joins by short levy name: `skagit_levy_crosswalk.levy_short = skagit_levy_composition.levy_short`.
- Land Ledger parcels are generated outputs keyed by `(city_slug, parcel_number)` and sourced from `v_land_ledger_source`.
- Tax delinquency statements join by `tax_delinquency_taxstatement.parcel_number = skagit_parcels.parcel_number`; secondary account match is `tax_account_number = skagit_parcels.account_number`.

## Row Counts

Counts from inspection:

| Relation | Rows |
| --- | ---: |
| `skagit_parcel_history` | 2,490,126 |
| `sales` | 351,693 |
| `improvements` | 308,649 |
| `parcel_zoning` | 126,329 |
| `land` | 106,617 |
| `assessor_sync_changes` | 90,991 |
| `assessor_rollup` | 83,639 |
| `skagit_parcels` | 83,638 |
| `skagit_parcel_history_status` | 83,272 |
| `gis_skagit_parcels` | 82,449 |
| `parcel_primary_zoning` | 72,040 |
| `skagit_levy_composition` | 28,161 |
| `waza_zoning_zones` | 12,600 |
| `land_ledger_parcels` | 3,971 |
| `tax_delinquency_taxstatement` | 1,621 |
| `skagit_levy_history` | 376 |
| `skagit_levy_crosswalk` | 91 |
| `land_ledger_city_summary` | 1 |

## Geometry Columns

All registered geometry columns are `geometry(MultiPolygon, 4326)`:

| Table or view | Geometry column |
| --- | --- |
| `gis_skagit_parcels` | `geometry` |
| `waza_zoning_zones` | `geometry` |
| `v_land_ledger_source` | `geometry` |
| `land_ledger_parcels` | `geometry` |

Spatial indexes:

- `gis_skagit_parcels` has GiST indexes on `geometry` and a btree index on `parcel_id`.
- `waza_zoning_zones` has GiST indexes on `geometry` and btree indexes on `jurisdiction` and `zone_id`.
- `land_ledger_parcels` has a GiST index on `geometry`, plus btree indexes on `city_slug` and `(city_slug, zone_id)`.

## Core Tables

### `skagit_parcels`

Primary assessor parcel table. Use for parcel attributes, owner/situs address, current taxes and values, levy code, property type, acreage, sale summary, and active/inactive status.

Important columns:

- Identity: `parcel_number`, `account_number`, `aid`
- Address: `situs_street_number`, `situs_street_name`, `situs_city_state_zip`
- Owner: `owner_name`, `owner_city`, `owner_state`, `owner_zip`
- Current values/taxes: `assessed_value`, `taxable_value`, `total_market_value`, `total_taxes`, `general_taxes`, `tax_statement_taxable_value`
- Land/use: `land_use`, `proptype`, `acres`, `levy_code`, `tax_year`, `appraisal_year`
- Sale summary: `sale_date`, `sale_price`, `sale_deed_type`
- Status: `inactive_date`

Indexes: `parcel_number`, `levy_code`, `owner_name`, `(situs_street_name, situs_street_number)`.

Code notes: `land_use` often stores both code and description in one formatted string, `proptype` is usually `R`, `P`, or `M`, and `utilities` stores comma-separated utility tokens. See `codes.md`.

### `gis_skagit_parcels`

GIS parcel polygons and GIS-facing attributes. Join to assessor parcels on `parcel_id`.

Columns: `objectid`, `parcel_id`, `situsstno`, `situsstname`, `situscsz`, `ownername`, `citydistrict`, `landuse`, `acres`, `taxyear`, `appraisalyear`, `inactivedate`, `geometry`.

### `parcel_primary_zoning`

One primary zoning record per parcel where available. Prefer this over `parcel_zoning` when a single zone per parcel is needed.

Columns: `parcel_id`, `citydistrict`, `landuse`, `acres`, `jurisdiction`, `county`, `zone_id`, `zone_name`, `waza_general`, `waza_specific`, `percent_of_parcel`, `overlap_area_sqft`, `parcel_area_sqft`, `reference_url`, `waza_spatial_normalization_date`.

Indexes: `parcel_id`, `zone_id`, `jurisdiction`.

### `parcel_zoning`

All parcel-zone overlaps, including non-primary zones.

Columns: `parcel_id`, `citydistrict`, `landuse`, `acres`, `zoning_objectid`, `jurisdiction`, `county`, `zone_id`, `zone_name`, `waza_general`, `waza_specific`, `reference_url`, `waza_spatial_normalization_date`, `parcel_area_sqft`, `overlap_area_sqft`, `percent_of_parcel`, `rn`, `is_primary`.

Indexes: `parcel_id`, `zone_id`, `jurisdiction`, `(parcel_id, is_primary)`.

### `waza_zoning_zones`

Zoning zone polygons from WAZA-normalized data.

Columns: `source_objectid`, `jurisdiction`, `county`, `zone_id`, `zone_name`, `waza_general`, `waza_specific`, `reference_url`, `waza_spatial_normalization_date`, `geometry`.

### `land_ledger_parcels`

Generated parcel-level Land Ledger outputs. Use this for productivity, opportunity, exclusion, scenario, and map API queries.

Columns: `city_slug`, `city_name`, `parcel_number`, `address`, `acres`, `land_use`, `category`, `zone_id`, `zone_name`, `zone_group`, `current_tax`, `tax_per_acre`, `city_tax_pct`, `allowed_scenarios`, `policy_scenarios`, `scenario_results`, `current_opportunity_10yr`, `policy_opportunity_10yr`, `benchmark_source`, `geometry`, `rebuilt_at`, `productivity_percentile`, `productivity_label`, `city_current_opportunity_10yr`, `city_policy_opportunity_10yr`, `exclusion_reasons`, `model_flags`, `assumption_version`.

Primary key/index: unique `(city_slug, parcel_number)`.

### `land_ledger_city_summary`

Generated city-level Land Ledger summary.

Columns: `city_slug`, `city_name`, `parcel_count`, `zoned_count`, `unknown_zone_count`, `current_opportunity_10yr`, `policy_opportunity_10yr`, `diagnostics`, `scenario_definitions`, `zone_descriptions`, `buildout_factor`, `horizon_years`, `rebuilt_at`, `city_current_opportunity_10yr`, `city_policy_opportunity_10yr`, `eligible_parcel_count`, `excluded_parcel_count`, `scenario_totals`, `exclusion_counts`, `assumption_version`.

### `v_land_ledger_source`

Source view for Land Ledger rebuilds. Prefer this when investigating why a parcel entered Land Ledger or when validating source inputs.

Columns: `city_slug`, `city_name`, `parcel_number`, `address`, `acres`, `land_use`, `assessed_value`, `taxable_value`, `total_taxes`, `city_tax_pct`, `zone_id`, `zone_name`, `zone_group`, `geometry`.

### `v_parcel_tax_summary`

Parcel tax contribution summary by agency.

Columns: `parcel_number`, `levy_code`, `parcel_tax_year`, `reporting_status`, `agency_name`, `mcag`, `sao_fit_url`, `total_tax`, `pct_of_bill`.

### `v_parcel_tax_detail`

Parcel tax line detail.

Columns: `parcel_number`, `levy_code`, `parcel_tax_year`, `levy_year`, `levy_short`, `levy_name`, `category`, `rate`, `assessed_value`, `tax_amount`, `entity_key`, `effective_mcag`, `reporting_status`, `sao_legal_name`, `sao_fit_url`, `review_needed`.

### `skagit_levy_composition`

Levy code composition by tax year and levy line.

Columns: `levy_code`, `tax_year`, `levy_short`, `levy_name`, `rate`, `category`.

Unique key: `(levy_code, tax_year, levy_short)`.

### `skagit_levy_crosswalk`

Maps levy short names to canonical entities and SAO/FIT reporting metadata.

Columns: `levy_short`, `levy_name_canonical`, `entity_key`, `mcag`, `reporting_status`, `parent_mcag`, `sao_legal_name`, `review_needed`, `sao_fit_url`.

### `skagit_levy_history`

Historical levy values/rates and SAO/FIT metadata.

Columns include `history_id`, `tax_year`, `taxing_district_code`, `county_code`, `district_name`, `levy_short`, `locally_assessed_value`, `levy_rate`, `district_levy`, `highest_prior_levy`, `new_construction_assessed_value`, `prior_year_levy_rate`, `maximum_allowable_levy_101_calc`, `entity_key`, `mcag`, `reporting_status`, `parent_mcag`, `sao_legal_name`, `review_needed`, `agency_common_name`, `agency_type`, `source_file`, `loaded_at`.

Indexes: `tax_year`, `levy_short`, `mcag`; unique `(tax_year, taxing_district_code)`.

### `v_skagit_levy_history_joined`

Joined levy history with effective MCAG and reporting metadata.

Use for questions about historical agency levies, reporting status, SAO links, and review flags.

### `v_skagit_agency_levy_history`

Agency-level levy history aggregation.

Columns: `history_id`, `tax_year`, `entity_key`, `effective_mcag`, `agency_name`, `reporting_status`, `agency_type`, `levy_line_count`, `district_levy`, `review_needed`.

### `skagit_parcel_history`

Historical parcel values/tax amounts fetched from parcel tax statement pages.

Columns: `parcel_number`, `tax_year`, `value_year`, `building_value`, `land_value`, `total_value`, `tax_amount`, `fetched_at`.

Primary key: `(parcel_number, tax_year)`.

### `tax_delinquency_taxstatement`

Tax statement/delinquency table.

Columns: `id`, `parcel_number`, `tax_account_number`, `tax_year`, `owner_name`, `situs_address`, `levy_code`, `general_tax`, `special_assessments_fees`, `total_due`, `amount_paid`, `status`, `lead_level`, `delinquent_installment_count`, `unpaid_installment_count`, `oldest_due_date`, `source_url`, `source_fetched_at`, `raw_data`, `created_at`, `updated_at`, `last_run_id`.

Useful indexes: `parcel_number`, `lead_level`, `(lead_level, total_due)`, `(source_fetched_at, parcel_number)`.

### `assessor_sync_*`

Use for assessor import/sync audit trails.

- `assessor_sync_runs`: run metadata, status, summary JSON, error text.
- `assessor_sync_files`: source file hashes and changed flags per run.
- `assessor_sync_changes`: per-record table changes with `old_row`, `new_row`, and `changed_fields` JSONB.
- `assessor_sync_reports`: run report text.

`assessor_sync_changes` is large. Filter by `run_id`, `table_name`, and `change_type`.

## Query Recipes

### Parcel Improvements With Code Definitions

```sql
SELECT
    i.parcelnumber AS parcel_number,
    i.imprv_id,
    i.segment_id,
    i.imprv_det_type_cd,
    COALESCE(i.imprv_det_type_description, type_map.description) AS type_description,
    i.imprv_det_class_cd,
    COALESCE(i.imprv_det_class_description, class_map.description) AS class_description,
    i.condition_cd,
    COALESCE(i.condition_description, condition_map.description) AS condition_description,
    i.imprv_val_num,
    i.living_area_num
FROM improvements i
LEFT JOIN code_mappings type_map
  ON type_map.category = 'improvement_type'
 AND type_map.code = upper(trim(i.imprv_det_type_cd))
LEFT JOIN code_mappings class_map
  ON class_map.category = 'improvement_class'
 AND class_map.code = upper(trim(i.imprv_det_class_cd))
LEFT JOIN code_mappings condition_map
  ON condition_map.category = 'condition'
 AND condition_map.code = upper(trim(i.condition_cd))
WHERE i.parcelnumber = :parcel_number
ORDER BY i.imprv_id, i.segment_id;
```

### Active Parcels With Geometry And Primary Zoning

```sql
SELECT
    p.parcel_number,
    concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
    p.situs_city_state_zip,
    p.owner_name,
    p.assessed_value,
    p.total_taxes,
    z.zone_id,
    z.zone_name,
    z.waza_general,
    ST_AsGeoJSON(g.geometry, 7)::json AS geometry
FROM skagit_parcels p
JOIN gis_skagit_parcels g
  ON g.parcel_id = p.parcel_number
LEFT JOIN parcel_primary_zoning z
  ON z.parcel_id = p.parcel_number
WHERE p.inactive_date IS NULL
  AND g.geometry IS NOT NULL
LIMIT 100;
```

### Parcels Inside A Bounding Box

```sql
SELECT p.parcel_number, p.owner_name, p.total_market_value
FROM gis_skagit_parcels g
JOIN skagit_parcels p
  ON p.parcel_number = g.parcel_id
WHERE g.geometry && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
  AND ST_Intersects(g.geometry, ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326))
  AND p.inactive_date IS NULL;
```

### Top Land Ledger Opportunities

```sql
SELECT
    city_slug,
    parcel_number,
    address,
    zone_id,
    zone_name,
    current_tax,
    city_current_opportunity_10yr,
    city_policy_opportunity_10yr,
    productivity_label,
    exclusion_reasons
FROM land_ledger_parcels
WHERE city_slug = :city_slug
ORDER BY city_policy_opportunity_10yr DESC NULLS LAST
LIMIT 50;
```

### Parcel Tax Breakdown

```sql
SELECT
    d.parcel_number,
    d.parcel_tax_year,
    d.levy_short,
    d.levy_name,
    d.category,
    d.rate,
    d.assessed_value,
    d.tax_amount,
    d.effective_mcag,
    d.reporting_status,
    d.sao_fit_url
FROM v_parcel_tax_detail d
WHERE d.parcel_number = :parcel_number
ORDER BY d.tax_amount DESC NULLS LAST;
```

### Delinquency Leads With Parcel Context

```sql
SELECT
    t.parcel_number,
    t.tax_year,
    t.owner_name,
    t.situs_address,
    t.total_due,
    t.amount_paid,
    t.lead_level,
    p.assessed_value,
    p.total_market_value,
    z.zone_name
FROM tax_delinquency_taxstatement t
LEFT JOIN skagit_parcels p
  ON p.parcel_number = t.parcel_number
LEFT JOIN parcel_primary_zoning z
  ON z.parcel_id = t.parcel_number
WHERE t.total_due > 0
ORDER BY t.total_due DESC
LIMIT 100;
```

### Recent Assessor Sync Changes

```sql
SELECT
    c.created_at,
    c.table_name,
    c.record_key,
    c.change_type,
    c.changed_fields
FROM assessor_sync_changes c
WHERE c.table_name = :table_name
ORDER BY c.created_at DESC
LIMIT 100;
```

## Django Code Pointers

- Settings and database URL precedence: `config/settings.py`
- Land Ledger SQL/API: `land_ledger/services.py`, `land_ledger/views.py`
- Tax tool SQL: `taxtool/queries.py`
- Tax delinquency sync: `tax_delinquency/sync.py`
- Assessor import/sync: `assessor_sync/management/commands/import_assessor.py`, `assessor_sync/management/commands/sync_assessor_data.py`
- Land Ledger migrations/views: `core/migrations/0002_land_ledger_tables.py`, `core/migrations/0003_land_ledger_source_values.py`

## Safety Notes

- Do not expose `.env` values.
- Prefer `LIMIT` while exploring large tables.
- Be careful with `assessor_sync_changes`, `skagit_parcel_history`, `sales`, and `improvements`; they are the largest tables.
- Use `ST_AsGeoJSON(..., 7)` for API geometry to keep payloads smaller.
- Confirm current counts live when freshness matters; this file is a useful map, not a data guarantee.
