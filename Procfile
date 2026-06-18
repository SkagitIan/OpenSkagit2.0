web: python manage.py migrate && python manage.py ensure_land_ledger --city sedro-woolley && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
