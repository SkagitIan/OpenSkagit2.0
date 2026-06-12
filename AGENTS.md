# AGENTS.md - OpenSkagit

You are working inside OpenSkagit, a Django application prepared for Railway.

## Current Phase

- Infrastructure only.
- Keep the app deploy-ready and minimal.
- Do not build product features until explicitly asked.

## Stack

- Django 5
- Python 3.12
- HTMX-ready server-rendered templates
- Tailwind CDN is allowed for future UI work
- WhiteNoise for static files
- SQLite locally by default
- PostgreSQL on Railway through `DATABASE_URL`

## Project Rules

- Use Django built-ins first.
- Keep pages in `templates/pages/`.
- Keep shared template fragments in `templates/partials/`.
- Keep static assets in `static/`.
- Do not hardcode secrets.
- Load local environment from `.env` with `load_dotenv()`.
- Keep `DATABASE_URL` support intact.

## Deployment Rules

- Railway starts from `Procfile`.
- `Procfile` must run migrations and collect static before Gunicorn starts.
- Static files must work after `python manage.py collectstatic --noinput`.
- The local app must boot with `python manage.py runserver`.

## Git Rules

- Work from the `railway-django-scratch` branch unless told otherwise.
- Avoid unrelated refactors.
- Do not delete or overwrite the original `OpenSkagit` workspace.
