# SFR Sales Modeling Dataset & Baseline Ratio Study — Plan

Status: pre-implementation plan, based on live inspection of the real database on 2026-07-13.
Goal of this milestone: prove `sales → clean SFR dataset → baseline models → ratio-study report` works end to end.
Explicitly out of scope: automated experiment loop, AI-generated market areas, IAAO compliance claims, updating
official assessed values, modifying source tables, mobile-friendly UI.

## 1. Actual fields found in each source table

Confirmed live via `information_schema.columns` and direct queries (not assumed from memory).

### `skagit_parcels` (typed mirror of `assessor_rollup`, 83,638 rows)
Key fields for this milestone: `parcel_number` (unique-ish, see risks), `neighborhood_code`, `land_use` (format
`(CODE) LABEL`, e.g. `(111) HOUSEHOLD, SFR, INSIDE CITY`), `proptype` (`R`/`P`/`M`), `assessed_value`,
`taxable_value`, `total_market_value`, `building_value`, `acres`, `tax_year`, `appraisal_year`, `inactive_date`
(real `date`, NULL when active), `buildingstyle`, `year_built`, `living_area` (parcel-level summary field —
NOT used as primary source; the improvement summary's `primary_living_area` is preferred since it's traceable to
one specific improvement row).

`assessor_rollup` additionally carries `land_use_description`, `neighborhood_description`, `neighborhood_code_id`
as separate description columns (all text, all as exported); `skagit_parcels` does not duplicate these, so the
SFR dataset build joins `assessor_rollup` for the human-readable description fields only.

### `sales` (352,213 rows; join key `parcel_number`)
- `sale_price_num` (real) — 208,300 rows > 0 out of 352,213 total.
- `sale_date_iso` (text, ISO format) — 344,858 rows match `^\d{4}-\d{2}-\d{2}$`.
- `deed_type` — dominated by `WARRANTY DEED` (181,749) and `QUIT CLAIM DEED` (106,345); also cryptic single-letter
  values `R`/`P`/`Z` and `''` (undetermined meaning, not decoded in `code_mappings`) and `MOBILE HOME DATA` (7,568).
- `sale_type` — **this is the assessor's own arms-length/validity flag**, not decorative metadata:
  `VALID SALE` (134,894) is the market-sale flag; other values (`QUITCLAIM` 38,933, `FAMILY` 31,067,
  `ESTATE`/`ESTATE SALE`, `FORCED SALE` 7,251, `GIFT DEED` 5,105, `TIMBER` 10,953, `WITH OTHER PROPERTY`,
  `PARTIAL INTEREST`, `RATIO <25% AND >175%` 2,690 — an explicit outlier flag) are non-market or already
  assessor-flagged as suspect and must be excluded from a ratio study.
- `reval_area` — a revaluation-area code (`103`, `101`, `320`, `100`, `11`, `311`, `317`, `330`, or `''`), purely
  descriptive; not a screening field.
- `recording_number`, `excise_number`, `saleid` — carried through as identifiers/debugging fields.

### `land` (106,623 rows across 81,083 distinct `parcelnumber` — mostly 1 segment/parcel, some multiple)
`land_type`, `appr_meth`, `size_acres_num` (real), `market_value_num` (real), `open_space_val` (text — non-empty
indicates current-use/open-space value present), `open_space_use_code_desc`.

### `improvements` (308,651 rows across only 54,146 distinct `parcelnumber` — average ~5.7 rows/parcel; many
parcels, e.g. vacant land, have zero rows)
`imprv_det_type_cd`/`imprv_det_type_description`, `imprv_det_class_cd`/`imprv_det_class_description`,
`condition_cd`/`condition_description`, `imprv_val_num` (real), `living_area_num` (real), `actual_year_built`,
`effective_yr_blt`, `bedrooms`, `rooms`. **Important:** `imprv_det_type_cd`/`imprv_det_class_cd`/`condition_cd`
are fixed-width text with trailing spaces (e.g. `'MA        '`) — every comparison must `TRIM()` first.

Verified: filtering `living_area_num > 0` cleanly isolates dwelling-contributing rows (`MA`, `MA2`, `MA1.5F`,
`UF2`, `UF1.5F`, `BMF`, `BMU`, `BMG`, `MW`, `LOFT`) with **zero** accessory rows (decks, porches, garages, sheds,
carports all have `living_area_num` NULL/0). This directly supports the milestone's "largest usable living area"
primary-improvement rule without needing a hand-maintained type-code allowlist.

### `parcel_geo_static_features` (83,281 rows; join key `parcel_number`) — built in the prior milestone, unchanged
here. All descriptive/geometry fields nullable; `feature_status` distinguishes `ok` from `missing_coordinates`.

### `parcel_primary_zoning` (72,040 rows; join key `parcel_id = parcel_number`)
`zone_id`, `zone_name`, `waza_general` (broad category: `RUR` 25,163, `LIR` 22,303, `NRL` 12,644, `MR` 2,692,
`MXU` 2,522, `IND` 2,098, `OS` 1,855, `COM` 1,850, `PUB` 803, `UND` 88, `NULL` 22), `waza_specific`,
`percent_of_parcel`. Not every parcel has a row (72,040 of 83,646) — left join, nullable.

## 2. Proposed SFR inclusion rules

Core detached-SFR `land_use` codes (from `code_mappings`/`landuse.csv`, cross-checked against real sold-parcel
volumes): **`110` (household SFR outside city) and `111` (household SFR inside city) only** for v1. These are by
far the dominant codes among valid, priced sales (29,980 and 55,321 rows respectively).

`112`/`113` (SFR with one/two-or-more secondary detached units) are **excluded from v1**, flagged with their own
reason (`secondary_detached_unit_present`), not lumped into "multifamily" — they are legitimate SFR by assessor
definition but a second/third structure on the same sale would confound a first-pass price-per-sqft model. This
can be revisited once the baseline is trusted.

`190` (vacation/cabin) is **excluded from v1** (`vacation_cabin_use`) — seasonal/cabin stock behaves differently
from year-round SFR and the milestone's exclusion list doesn't explicitly address it, so it's flagged separately
rather than silently folded into "included" or a generic "excluded" bucket.

Hard exclusions (by `land_use` code prefix, cross-checked against `proptype` and `buildingstyle`):
- Manufactured/mobile: `180`, `181`, `182`, `185`, `150` — confirmed by `proptype = 'M'` (2,473 of 2,477 non-`R`
  priced valid sales) and `buildingstyle` values like `DOUBLE WIDE`.
- Condo: `140`, `500`, `970`.
- Multi-family: `120`, `130`, `112`, `113` (112/113 tracked separately per above).
- Hotel/institutional lodging: `160`, `170`.
- Commercial/industrial/utility (`2xx`–`6xx`, `460`, `470`, `480`, `490`): excluded wholesale.
- Recreation/cultural/agriculture (`7xx`, `8xx`): excluded wholesale, including `830` current-use farm (explicit
  "agricultural-only" exclusion).
- Vacant/undeveloped/open-space (`9xx`: `910`, `911`, `912`, `920`, `930`, `940`, `941`): excluded ("vacant land").

Even within `110`/`111`, `buildingstyle` values `TOWNHOUSE - ATTACHED SFR UNITS` and `CONDO` appear (172 and 51
sales respectively) — excluded regardless of land_use code (`attached_or_condo_buildingstyle`).

`proptype` must be `R`; `M` and `P` are excluded regardless of land_use code (belt-and-suspenders check).

## 3. Proposed sale validity rules

- `sale_price_num` present and `> 0`.
- `sale_date_iso` matches `^\d{4}-\d{2}-\d{2}$` (guarded cast, per existing codebase convention in `ai_search.py`).
- `sale_type = 'VALID SALE'` — the assessor's own arms-length flag. Every other `sale_type` value is excluded
  with reason `non_arms_length_sale_type` (detail = the actual sale_type value, e.g. `FAMILY`, `FORCED SALE`).
- Parcel must match an active row in `skagit_parcels`/`assessor_rollup` (`inactive_date IS NULL`).
- Parcel must have a usable improvement summary (`model_improvement_summary` row with `primary_living_area > 0`
  and a resolvable year built, i.e. `primary_actual_year_built` or `primary_effective_year_built` present).

## 4. Land aggregation logic (`model_land_summary`)

One row per `land.parcelnumber`, built with a single grouped SQL aggregation (no per-row Python loop):
- `land_segment_count` = `COUNT(*)`
- `total_land_acres` = `SUM(size_acres_num)`
- `total_land_market_value` = `SUM(market_value_num)`
- `primary_land_type` = `land_type` of the segment with `MAX(size_acres_num)` (largest segment defines the
  parcel's dominant land character; ties broken by highest `market_value_num`, then lowest `id`)
- `primary_appr_method` = `appr_meth` from that same primary segment
- `has_open_space_value` = `bool_or(open_space_val IS NOT NULL AND open_space_val <> '' AND open_space_val <> '0')`
- `max_land_segment_acres` = `MAX(size_acres_num)`
- `max_land_segment_value` = `MAX(market_value_num)`

Implementation: a `DISTINCT ON (parcelnumber) ORDER BY parcelnumber, size_acres_num DESC NULLS LAST, market_value_num
DESC NULLS LAST, id` subquery for the "primary segment" columns, joined to a plain `GROUP BY parcelnumber`
aggregate for the count/sum/max columns. Both are set-based SQL, no row-by-row Python.

## 5. Improvement aggregation logic (`model_improvement_summary`)

One row per `improvements.parcelnumber`:
- Primary improvement = the row with `MAX(living_area_num)` (nulls/zeros last); if every row for a parcel has
  null/zero `living_area_num`, fall back to `MAX(imprv_val_num)`. Selection uses `DISTINCT ON` with an explicit
  `ORDER BY parcelnumber, (living_area_num > 0) DESC, living_area_num DESC NULLS LAST, imprv_val_num DESC NULLS
  LAST, imprv_id` so the tie-break is deterministic and reproducible.
- `improvement_row_count` = `COUNT(*)` (all rows, including accessory structures — debugging/context field).
- `building_count` = `COUNT(*) FILTER (WHERE living_area_num > 0)` — distinct dwelling-contributing structures
  (approximates "how many separate living-area buildings", relevant for spotting `112`/`113`-style parcels).
- `total_improvement_value` = `SUM(imprv_val_num)` (all rows — main area + garage + deck etc., i.e. total
  improvement value on the parcel, not just the primary structure).
- `total_living_area` = `SUM(living_area_num)` (all dwelling-contributing rows — catches multi-row main areas,
  e.g. `MA` + `UF2` + `BMF` on the same house).
- `primary_living_area`, `primary_building_style`, `primary_condition_cd`, `primary_condition_description`,
  `primary_imprv_det_type_cd`, `primary_imprv_det_class_cd`, `primary_imprv_det_type_description`,
  `primary_imprv_det_class_description`, `primary_actual_year_built`, `primary_effective_year_built`,
  `primary_imprv_id` — all pulled from the one selected primary row (the `primary_imprv_id` is kept specifically
  so a human can look up *which* row was chosen and audit the selection).
- `bedrooms`, `rooms` — from the primary row (per-improvement fields in this schema, not parcel-level).
- `has_garage` = `bool_or(TRIM(imprv_det_type_cd) IN ('AGAR','DGAR','GBI','CARP'))`
- `has_fireplace` = `bool_or(TRIM(imprv_det_type_cd) = 'OFP')` — verified live: `OFP` is the only fireplace-like
  type code in the real data (no `FPL` or similar exists).
- `has_basement` = `bool_or(TRIM(imprv_det_type_cd) IN ('BMF','BMU','BMG','GBI'))`

`bedrooms`/`rooms` in this schema are per-improvement-row text fields, sourced from the primary row (not summed
across accessory rows, which would be meaningless). **Verified live: these are sparse** — of 296,846 rows with
`living_area_num > 0`, 254,699 (86%) have `bedrooms = ''` (empty string, not NULL). Implementation casts `''` to
NULL before use; the dataset summary report surfaces this null rate honestly rather than defaulting to 0.

## Sale volume note

Of the 208,300 sales with a positive price, 344,858 of the full 352,213 sales have a valid ISO date. After
applying `sale_type = 'VALID SALE'` (134,894 total) and the core `110`/`111` land-use restriction, the retained
SFR count will be meaningfully smaller than either number alone — the exact retained count is a build-time
diagnostic, not assumed here.

## 6. Join keys

| From | To | Key |
| --- | --- | --- |
| `sales` | `skagit_parcels` | `sales.parcel_number = skagit_parcels.parcel_number` |
| `sales` | `assessor_rollup` | `sales.parcel_number = assessor_rollup.parcel_number` (description fields only) |
| `sales` | `model_land_summary` | `sales.parcel_number = model_land_summary.parcel_number` |
| `sales` | `model_improvement_summary` | `sales.parcel_number = model_improvement_summary.parcel_number` |
| `sales` | `parcel_geo_static_features` | `sales.parcel_number = parcel_geo_static_features.parcel_number` |
| `sales` | `parcel_primary_zoning` | `sales.parcel_number = parcel_primary_zoning.parcel_id` |

All joins are `LEFT JOIN` from `sales` outward — a sale is never dropped because a downstream table lacks a row;
missing geo/zoning/land/improvement data is instead a `NULL` and, where it matters for SFR validity (improvement
summary), an explicit exclusion reason.

**Known duplicate-key risk:** `assessor_rollup`/`skagit_parcels.parcel_number` is not perfectly unique (83,646
rows / 83,527 distinct in `assessor_rollup`, confirmed in the geo-features milestone). The parcel join must
dedupe (`DISTINCT ON (parcel_number)`, preferring the active row) before joining to sales, exactly like the
land/improvement one-to-many joins, or sale rows would silently multiply.

## 7. Expected output columns

`model_sfr_sales_dataset` / `data/processed/sfr_sales_model_dataset.parquet` — one row per valid SFR sale, columns
exactly as enumerated in the milestone brief (sale fields, parcel fields, land summary fields, improvement summary
fields, geo feature fields, zoning fields), plus:
- `dataset_version = 'prototype_current_characteristics'` (string label, stamped on every row)
- `built_at` (timestamp, when this dataset build ran)

`log_sale_price` = `ln(sale_price)`, computed once during the build, not recomputed downstream.

## 8. Known risks

1. **Temporal leakage** (explicit, required warning): current parcel/improvement characteristics are joined to
   historical sales. A parcel that added a garage in 2024 shows that garage against a 2015 sale. Labeled
   `prototype_current_characteristics` everywhere; warning text reproduced verbatim from the brief in both the
   dataset summary and ratio-study reports.
2. **Duplicate parcel_number rows** in `assessor_rollup`/`skagit_parcels` (see §6) — must dedupe before joining or
   sale counts silently inflate.
3. **112/113/190 boundary calls** are judgment calls, not hard facts from the data — documented above and surfaced
   in the diagnostic report so they can be revisited with real distribution numbers, not just code definitions.
4. **`sale_price_num` real-vs-text**: `sales.sale_price` is text, `sale_price_num` is the parsed real column;
   using the wrong one would silently produce nonsense. Always use the `_num` column.
5. **Small-group ratio stats**: many neighborhoods/school districts will have `n < 30` sales; report follows the
   brief's `n >= 30` / `15–29` provisional / `<15` insufficient bands rather than a single pass/fail number.
6. **`bedrooms`/`rooms`/fireplace fields**: not independently verified against real distinct values in this pass
   (time-boxed); implementation will re-check before trusting them and fall back to `null`/`false` rather than a
   guess if the signal turns out unreliable.
7. **No mobile UI**: reports are desktop-oriented HTML/CSV only, per the brief.

## 9. Commands to be added (new `regression` app)

- `python manage.py build_sfr_sales_model_dataset` — builds `model_land_summary`, `model_improvement_summary`,
  runs the SFR classification diagnostic, writes `model_sfr_sales_exclusions`, builds `model_sfr_sales_dataset` +
  `data/processed/sfr_sales_model_dataset.parquet`, and `data/reports/sfr_sales_dataset_summary.{html,md}`.
  Supports `--dry-run` (report only, no writes) consistent with this repo's existing command conventions.
- `python manage.py run_sfr_baseline_ratio_study` — consumes the parquet, trains the 4 baseline models
  (assessed-value baseline, price/sqft by neighborhood, linear regression, ridge regression) on an 80/20 fixed-seed
  split, computes ratio-study metrics county-wide and by group, and writes
  `data/reports/sfr_baseline_ratio_study.html` + the 6 CSVs listed in the brief.

Both commands are read-only with respect to every source table (`sales`, `land`, `improvements`, `skagit_parcels`,
`assessor_rollup`, `parcel_geo_static_features`, `parcel_primary_zoning`) — they only ever write to the new
`regression` app's own tables and to `data/processed/` / `data/reports/`.
