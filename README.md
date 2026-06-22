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
