# OpenSkagit

Fresh Django/Railway foundation for OpenSkagit.

## Local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
# Set NEW_DATABASE_URL, POSTGIS_DATABASE_URL, or DATABASE_URL to the PostGIS database.
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 8004
```

The local `.env` file is loaded with `load_dotenv()` from `config/settings.py`.
SQLite fallback has been removed; OpenSkagit expects PostgreSQL/PostGIS in every environment.

## Railway

Railway can deploy this repo/branch with the included `Procfile` or `railway.json`.

Required variables:

- `SECRET_KEY`
- `DEBUG=false`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `NEW_DATABASE_URL`, `POSTGIS_DATABASE_URL`, or `DATABASE_URL` pointing at the Railway PostGIS database. Django checks them in that order.

Static files are served by WhiteNoise and collected into `staticfiles/`.

## Nightly Assessor Sync

Run the Skagit County Assessor sync manually:

```powershell
python manage.py sync_assessor_data
```

The command downloads `SkagitAssessmentData.zip`, stages the assessor rollup, sales,
land, and improvement files, compares them with the existing PostGIS tables, inserts
new keyed records, replaces changed keyed records, records row-level changes in
`assessor_sync_changes`, stores file hashes in `assessor_sync_files`, and writes a
Markdown report to `output/assessor_sync_reports/`.

For Railway, create a separate service that uses this same repo and set its config
file path to `/railway.assessor-sync.json`. That service runs:

```bash
python manage.py sync_assessor_data
```

The included cron schedule is `0 10 * * *`, which Railway evaluates in UTC.

## GIS Source Sync

`sync_gis_sources` keeps clean local copies of Skagit County GIS source
shapefiles and tracks whether each one changed. This is the foundation step for
later parcel geographic feature work — it only downloads, hashes, unzips, and
records sources. It does **not** build parcel features, import into PostGIS, or
run analysis.

### Where sources are configured

Layers live in [`data/gis/sources/gis_sources.yaml`](data/gis/sources/gis_sources.yaml).
Each entry has a `url`, `display_name`, `enabled` flag, `expected_geometry_type`,
and `refresh_frequency`. Replace the placeholder URLs with the real Skagit GIS
download URLs (see the [county GIS catalog](https://www.skagitcounty.net/Departments/GIS/Digital/main.htm))
as they are confirmed. Set `enabled: false` to skip a layer without deleting it.

Downloaded files are written under `data/gis/` (git-ignored):

```text
data/gis/raw/<layer>/source.zip        # raw download + source_hash.txt + downloaded_at.txt
data/gis/extracted/<layer>/            # validated shapefile (.shp/.shx/.dbf/.prj, etc.)
```

### Run all sources

```powershell
python manage.py sync_gis_sources
```

Each enabled layer is downloaded, SHA-256 hashed, and compared to the hash
stored in the `gis_sources` table. Only layers whose hash changed are
re-extracted; the previous extracted folder is preserved until a new download
**and** extraction both succeed. One failing layer never stops the others.

### Run a single layer

```powershell
python manage.py sync_gis_sources --layer zoning
```

### Force a refresh

Re-download and re-extract even when the hash looks unchanged:

```powershell
python manage.py sync_gis_sources --force
```

### Preview without writing

```powershell
python manage.py sync_gis_sources --dry-run
```

`--dry-run` reports what would happen without downloading, writing files, or
touching the database.

### Which layers changed

The end-of-run summary lists changed, unchanged, failed, and disabled layers,
plus each layer's raw and extracted paths. Per-layer status is also stored in
the `gis_sources` table (`last_status`, `last_changed_at`, `last_error`, hashes)
and is browsable read-only in the Django admin under **Assessor Sync → GIS
sources**. Statuses are `never_synced`, `unchanged`, `changed`,
`download_failed`, `extract_failed`, and `disabled`.

## Static Parcel Geography Features

`build_geo_features` builds one row per active parcel of precomputed geography
that rarely changes -- containing city/comp-plan designation/school
district/fire district/voting precinct, nearest road/public place/tide gate,
and distance to five fixed city anchors (Mount Vernon, Burlington,
Sedro-Woolley, Anacortes, La Conner). It reads the shapefiles
`sync_gis_sources` already extracted under `data/gis/extracted/`, so run that
command first. This step only computes static geography -- no regression
models, no nearby-sales features, no GIS warehouse.

Each parcel's point is resolved in order: assessor X/Y (not present in the
current assessor export), the county's PNumbers point layer, or the parcel
polygon's centroid as a fallback. All spatial work happens in EPSG:2926
(Washington State Plane North, US feet), matching the source shapefiles;
`lat`/`lon` are reprojected to WGS84 only for convenience.

```powershell
python manage.py build_geo_features
```

By default (`--missing-or-changed`) it rebuilds only parcels with no feature
row yet, a changed resolved coordinate or point source, a prior `failed`
status, or a stale `feature_version`. Other flags:

```powershell
python manage.py build_geo_features --full              # rebuild every active parcel
python manage.py build_geo_features --parcel P123456     # rebuild one parcel
python manage.py build_geo_features --limit 200          # cap how many parcels are rebuilt (testing)
```

The summary reports active parcels checked, parcels needing rebuild, parcels
updated, parcels missing coordinates, parcels failed, and runtime. One bad
parcel is marked `feature_status = failed` and never stops the rest of the
run; parcels with no resolvable point are marked `missing_coordinates`.
Results are browsable read-only in the Django admin under **Assessor Sync →
Parcel geo static features**.

### Export to Parquet

```powershell
python manage.py export_geo_features_parquet
```

Writes the full table to `data/processed/parcel_geo_static_features.parquet`.

## SFR Sales Modeling Dataset & Baseline Ratio Study

The `regression` app builds the first SFR (single-family residential) sales
modeling dataset and a baseline valuation/ratio-study tool -- a prototype that
proves `sales → clean SFR dataset → baseline models → ratio-study report`
works end to end. No automated experiment loop, no AI-generated market areas,
no IAAO compliance claim, and no update to official assessed values. See
[`docs/sfr_modeling_dataset_plan.md`](docs/sfr_modeling_dataset_plan.md) for
the full inclusion/exclusion rules and the real data evidence behind them.

```powershell
python manage.py build_sfr_sales_model_dataset
```

Rebuilds, in order: `model_land_summary` and `model_improvement_summary` (one
row per parcel, aggregated with set-based SQL from the one-to-many `land` and
`improvements` tables), then `model_sfr_sales_dataset` (one row per valid SFR
sale) and `model_sfr_sales_exclusions` (every excluded sale with a reason).
Reads only from source tables (`sales`, `land`, `improvements`,
`skagit_parcels`, `assessor_rollup`, `parcel_geo_static_features`,
`parcel_primary_zoning`) -- never writes to them. Also exports:

- `data/processed/sfr_sales_model_dataset.parquet`
- `data/processed/sfr_sales_exclusions.parquet`
- `data/reports/sfr_sales_dataset_summary.{html,md}`
- `data/reports/sfr_classification_diagnostic.md` (the distinct-value evidence behind the SFR rules)

The dataset is labeled `dataset_version = 'prototype_current_characteristics'`
everywhere -- it joins **current** parcel/improvement characteristics to
**historical** sales, which can contain temporal leakage. Use `--dry-run` to
preview the summary without writing anything.

```powershell
python manage.py run_sfr_baseline_ratio_study
```

Trains 4 baseline models on a fixed 80/20 split (seed 42): the existing
assessed value, price-per-sqft by neighborhood, linear regression on log sale
price, and ridge regression on log sale price. **Defaults to the most recent 5
sale years** (`--recent-years`, pass `0` to disable) -- comparing today's
assessed values/predictions against decades-old sale prices measures market
appreciation, not model quality; on this data assessed/sale-price ratios run
40x+ for 1960s sales and only settle near 1.0 in the last few years. Writes:

- `data/reports/sfr_baseline_ratio_study.html`
- `data/reports/sfr_baseline_model_summary.csv`
- `data/reports/sfr_baseline_ratio_study_by_{neighborhood,city,comp_plan,school_district,sale_year,price_decile}.csv`

Group reports (by neighborhood/city/comp plan/school district/sale year/price
decile) use the ridge regression model. Every group table labels its sample
size `normal` (n≥30), `provisional_low_sample` (15–29), or
`insufficient_sample` (<15) rather than reporting a pass/fail number on a
handful of sales. This is a baseline report only -- no IAAO compliance claim.
