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
