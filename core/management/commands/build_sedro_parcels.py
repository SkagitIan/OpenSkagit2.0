"""
Django management command: build_sedro_parcels

Rebuilds static/data/sedro_woolley_parcels.geojson from the PostGIS database.
Queries parcel attributes, tax share, zoning (parcel_primary_zoning), and
geometry (gis_skagit_parcels) — no local shapefiles required.

Usage (Railway Console or local):
    python manage.py build_sedro_parcels

The output file is read by the Land Ledger map on /cities/sedro-woolley/.
After running, commit and push static/data/sedro_woolley_parcels.geojson
so the new file is picked up on the next deploy.

If the zoning data lives in a separate PostGIS database, set NEW_DATABASE_URL
in Railway Variables and it will be used instead of DATABASE_URL.
"""
import importlib
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rebuild static/data/sedro_woolley_parcels.geojson from PostGIS"

    def handle(self, *args, **options):
        # Import the script as a module so we don't duplicate logic.
        # sys.path already includes the project root when manage.py runs.
        from django.conf import settings
        script_path = settings.BASE_DIR / "data" / "build_sedro_parcels.py"
        spec = importlib.util.spec_from_file_location("build_sedro_parcels", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.stdout.write("Starting Land Ledger GeoJSON rebuild...")
        try:
            mod.main()
            self.stdout.write(self.style.SUCCESS("Done. Commit static/data/sedro_woolley_parcels.geojson to deploy."))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Build failed: {exc}"))
            sys.exit(1)
