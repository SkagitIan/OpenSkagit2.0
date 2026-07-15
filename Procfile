web: python manage.py migrate && python manage.py sync_public_intelligence && python manage.py ensure_land_ledger --city sedro-woolley && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
tax-backfill: python manage.py migrate && python manage.py backfill_tax_statements --years 2023 2024 2025 2026 --delay ${TAX_DELINQUENCY_DELAY:-0.35}
tax-slow-check: python manage.py migrate && python manage.py slow_check_tax_statements --years 2023 2024 2025 2026 --cycle-hours ${TAX_DELINQUENCY_CYCLE_HOURS:-168}
