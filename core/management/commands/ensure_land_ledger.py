from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.land_ledger import ASSUMPTION_VERSION, CITY_CONFIGS, rebuild_land_ledger


class Command(BaseCommand):
    help = "Ensure durable Land Ledger rows exist for the current model version."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--city", dest="city_slug", help="City slug to ensure, e.g. sedro-woolley")
        group.add_argument("--all", action="store_true", dest="all_cities", help="Ensure every configured city")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild even when rows already exist for the current assumption version.",
        )

    def handle(self, *args, **options):
        if options["all_cities"]:
            city_slugs = list(CITY_CONFIGS)
        elif options["city_slug"]:
            city_slugs = [options["city_slug"]]
        else:
            city_slugs = ["sedro-woolley"]

        unknown = [slug for slug in city_slugs if slug not in CITY_CONFIGS]
        if unknown:
            raise CommandError(f"Unknown city slug(s): {', '.join(unknown)}")

        stale = city_slugs if options["force"] else self._stale_city_slugs(city_slugs)
        if not stale:
            self.stdout.write(self.style.SUCCESS("Land Ledger is already populated for the current model version."))
            return

        self.stdout.write(f"Rebuilding Land Ledger for: {', '.join(stale)}")
        results = rebuild_land_ledger(stale)
        for result in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{result.city_slug}: {result.parcel_count:,} parcels, "
                    f"{result.zoned_count:,} zoned, {result.unknown_zone_count:,} unknown zones"
                )
            )

    def _stale_city_slugs(self, city_slugs):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT city_slug, parcel_count, assumption_version
                FROM land_ledger_city_summary
                WHERE city_slug = ANY(%s)
                """,
                [city_slugs],
            )
            rows = {
                city_slug: {
                    "parcel_count": parcel_count,
                    "assumption_version": assumption_version,
                }
                for city_slug, parcel_count, assumption_version in cursor.fetchall()
            }

        stale = []
        for city_slug in city_slugs:
            row = rows.get(city_slug)
            if not row:
                stale.append(city_slug)
            elif not row["parcel_count"]:
                stale.append(city_slug)
            elif row["assumption_version"] != ASSUMPTION_VERSION:
                stale.append(city_slug)
        return stale
