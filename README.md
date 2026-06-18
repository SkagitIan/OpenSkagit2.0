# OpenSkagit

Fresh Django/Railway foundation for OpenSkagit.

## Local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 8004
```

The local `.env` file is loaded with `load_dotenv()` from `config/settings.py`.

## Railway

Railway can deploy this repo/branch with the included `Procfile` or `railway.json`.

Required variables:

- `SECRET_KEY`
- `DEBUG=false`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` when using Railway Postgres
- `POSTGIS_DATABASE_URL` or `NEW_DATABASE_URL` for the migrated Railway PostGIS database. When either is set, Django uses it before `DATABASE_URL` and switches to the GeoDjango PostGIS backend.

Static files are served by WhiteNoise and collected into `staticfiles/`.
