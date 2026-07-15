# AGENTS.md - OpenSkagit

You are working inside OpenSkagit, a Django application prepared for Railway.

## Windows Editing Rules

This repo often runs in a Windows managed sandbox where `apply_patch` can fail with:

`windows unelevated restricted-token sandbox cannot enforce split writable root sets directly`

When that happens, do not retry `apply_patch`. Use a narrowly scoped PowerShell edit with repo-relative paths, then immediately run `git diff -- <changed files>` to verify the exact change.

Keep sandbox/tool fallback chatter out of user-facing progress updates unless the user asks. Report only the final relevant outcome.

## Stack

- Django 5
- Python 3.12
- Server-rendered templates with HTMX-style partials where useful
- WhiteNoise for static files
- PostgreSQL/PostGIS on Railway through `NEW_DATABASE_URL`, `POSTGIS_DATABASE_URL`, or `DATABASE_URL`
- Local `.env` is loaded by `config/settings.py`
- SQLite fallback has been removed; every environment must set `NEW_DATABASE_URL`, `POSTGIS_DATABASE_URL`, or `DATABASE_URL`.

## Feature App Boundaries

Keep major features isolated in their owning Django app:

- `taxtool`: the `/tax/` parcel tax tool, tax templates, tax views, tax utilities, tax management commands.
- `land_ledger`: Land Ledger services, API endpoints, durable Land Ledger table wrappers, admin, and `rebuild_land_ledger` / `ensure_land_ledger` commands.
- `assessor_sync`: Skagit County Assessor import/sync commands, nightly sync audit models/admin, and Railway cron support.
- `ask_agent`: `/ask/` UI endpoints, streaming responses, DuckDB analysis helpers, and OpenSkagit MCP tool integration.
- `discovery_agent`: Current/discovery probes, Current draft model/admin, and discovery management commands.
- `graph`: Internal parcel relationship graph entity resolution, adjacency, Kuzu builds, pattern results, and graph query tooling; no owner/entity/address identity may cross its public serving boundary.
- `core`: shared site shell only: home/city pages, auth URL wiring, shared context processors, shared template tags, and legacy compatibility shims.

Do not add new feature code to `core` when one of the feature apps above owns it. If a cross-feature helper is needed, prefer a small shared module only after checking whether one feature should own it.

## Database Rules

- Keep existing PostGIS table names stable unless a migration plan is explicit.
- Existing imported/audit/spatial tables are exposed through unmanaged Django models.
- Admin views for imported/audit/spatial data should stay read-only unless the user explicitly asks for editing.
- Keep `DATABASE_URL`, `POSTGIS_DATABASE_URL`, and `NEW_DATABASE_URL` support intact.
- Do not reintroduce SQLite fallback or commit local database files.

## Templates And Static

- Keep page templates in `templates/pages/`.
- Keep shared fragments in `templates/partials/`.
- Feature-specific templates may live in the feature app when they are not shared.
- Keep static assets in `static/`.

## Deployment Rules

- Railway web deploy starts from `railway.json` or `Procfile`.
- The web process must run migrations and collect static before Gunicorn starts.
- The assessor sync cron service uses `railway.assessor-sync.json` and runs `python manage.py sync_assessor_data`.
- Static files must work after `python manage.py collectstatic --noinput`.
- The local app must boot with `python manage.py runserver`.

## Git Rules

- Work from the `railway-django-scratch` branch unless told otherwise.
- Avoid unrelated refactors.
- Do not delete or overwrite the original `OpenSkagit` workspace.
- The worktree may contain unrelated local changes; stage only files relevant to the current task.
