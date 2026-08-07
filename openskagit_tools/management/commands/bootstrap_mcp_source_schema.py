from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


SOURCE_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS assessor_rollup (
    parcel_number TEXT PRIMARY KEY,
    proptype TEXT,
    total_market_value_num NUMERIC,
    city_district TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    parcel_number TEXT,
    sale_price_num NUMERIC,
    sale_date_iso TEXT,
    sale_type TEXT
);

CREATE TABLE IF NOT EXISTS parcel_zoning (
    parcel_id TEXT,
    is_primary BOOLEAN,
    percent_of_parcel NUMERIC,
    overlap_area_sqft NUMERIC,
    zone_id TEXT,
    zone_name TEXT
);

CREATE TABLE IF NOT EXISTS v_parcel_tax_summary (
    parcel_number TEXT,
    total_tax NUMERIC,
    mcag TEXT
);

CREATE TABLE IF NOT EXISTS skagit_parcels (
    parcel_number TEXT PRIMARY KEY,
    city_district TEXT,
    inactive_date DATE,
    acres NUMERIC,
    total_taxes NUMERIC,
    situs_street_number TEXT,
    situs_street_name TEXT,
    land_use TEXT,
    assessed_value NUMERIC,
    taxable_value NUMERIC
);

CREATE TABLE IF NOT EXISTS gis_skagit_parcels (
    parcel_id TEXT PRIMARY KEY,
    geometry geometry(MultiPolygon, 4326)
);

CREATE TABLE IF NOT EXISTS parcel_primary_zoning (
    parcel_id TEXT PRIMARY KEY,
    zone_id TEXT,
    zone_name TEXT
);

CREATE TABLE IF NOT EXISTS waza_zoning_zones (
    zone_id TEXT PRIMARY KEY,
    zone_name TEXT,
    geometry geometry(MultiPolygon, 4326)
);
"""

SAMPLE_SQL = """
INSERT INTO assessor_rollup (parcel_number, proptype, total_market_value_num, city_district)
VALUES ('DEV0001', 'R', 100000, 'Sedro Woolley')
ON CONFLICT (parcel_number) DO NOTHING;

INSERT INTO skagit_parcels (
    parcel_number, city_district, acres, total_taxes, situs_street_number,
    situs_street_name, land_use, assessed_value, taxable_value
)
VALUES ('DEV0001', 'Sedro Woolley', 1, 1000, '1', 'LOCAL TEST WAY', 'RESIDENTIAL', 100000, 100000)
ON CONFLICT (parcel_number) DO NOTHING;

INSERT INTO gis_skagit_parcels (parcel_id, geometry)
VALUES (
    'DEV0001',
    ST_GeomFromText(
        'MULTIPOLYGON(((-122.4 48.4,-122.4 48.401,-122.399 48.401,-122.399 48.4,-122.4 48.4)))',
        4326
    )
)
ON CONFLICT (parcel_id) DO NOTHING;
"""

REQUIRED_RELATIONS = (
    "assessor_rollup",
    "sales",
    "parcel_zoning",
    "v_parcel_tax_summary",
    "skagit_parcels",
    "gis_skagit_parcels",
    "parcel_primary_zoning",
    "waza_zoning_zones",
)


class Command(BaseCommand):
    help = "Create minimal source relations for an isolated development/test PostGIS database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-sample",
            action="store_true",
            help="Insert one synthetic parcel with a text parcel key.",
        )

    @staticmethod
    def _verify_release_candidate_database(cursor, *, environment_id: str) -> None:
        if not environment_id:
            raise CommandError("Railway release-candidate database marking requires RAILWAY_ENVIRONMENT_ID.")

        cursor.execute(
            """
            SELECT
                to_regclass('public.openskagit_release_environment_marker'),
                to_regclass('public.django_migrations'),
                to_regclass('public.openskagit_tools_mcpoauthclient')
            """
        )
        marker_relation, migrations_relation, oauth_relation = cursor.fetchone()

        if marker_relation:
            cursor.execute("SELECT environment_id FROM openskagit_release_environment_marker")
            marked_environment = cursor.fetchone()
            if not marked_environment or marked_environment[0] != environment_id:
                raise CommandError("Release-candidate database marker belongs to another environment.")
            return

        if migrations_relation or oauth_relation:
            raise CommandError(
                "Refusing to initialize an unmarked release-candidate database that already "
                "contains application or OAuth schema."
            )

        cursor.execute(
            """
            CREATE TABLE openskagit_release_environment_marker (
                environment_id TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "INSERT INTO openskagit_release_environment_marker (environment_id) VALUES (%s)",
            [environment_id],
        )

    def handle(self, *args, **options):
        local_environment = settings.OPENSKAGIT_ENVIRONMENT in {"development", "test"}
        railway_name = os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
        rc_environment = (
            settings.OPENSKAGIT_ENVIRONMENT == "release-candidate"
            and os.getenv("OPENSKAGIT_ALLOW_RC_SAMPLE_BOOTSTRAP", "").lower() == "true"
            and any(marker in railway_name for marker in ("rc", "candidate", "staging"))
            and options["with_sample"]
        )
        if not (local_environment or rc_environment):
            raise CommandError(
                "Source bootstrap is restricted to local/test or an explicitly marked "
                "Railway release-candidate environment."
            )

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(SOURCE_SCHEMA_SQL)
                if options["with_sample"]:
                    cursor.execute(SAMPLE_SQL)
                cursor.execute(
                    "SELECT relname FROM pg_class WHERE relname = ANY(%s)",
                    [list(REQUIRED_RELATIONS)],
                )
                present = {row[0] for row in cursor.fetchall()}
                missing = sorted(set(REQUIRED_RELATIONS) - present)
                if missing:
                    raise CommandError(f"Source bootstrap verification failed: missing={missing}")

        suffix = " with synthetic sample data" if options["with_sample"] else ""
        self.stdout.write(
            self.style.SUCCESS(f"Verified {len(REQUIRED_RELATIONS)} local PostGIS source relations{suffix}.")
        )
