from django.core.management.base import BaseCommand, CommandError

from land_ledger.services import CITY_CONFIGS, rebuild_land_ledger


class Command(BaseCommand):
    help = "Rebuild durable Land Ledger tables from PostGIS source tables."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--city", dest="city_slug", help="City slug to rebuild, e.g. sedro-woolley")
        group.add_argument("--all", action="store_true", dest="all_cities", help="Rebuild every configured city")

    def handle(self, *args, **options):
        if options["all_cities"]:
            city_slugs = list(CITY_CONFIGS)
        else:
            city_slugs = [options["city_slug"]]

        try:
            results = rebuild_land_ledger(city_slugs)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        for result in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{result.city_slug}: {result.parcel_count:,} parcels, "
                    f"{result.zoned_count:,} zoned, {result.unknown_zone_count:,} unknown zones, "
                    f"current ${result.current_opportunity_10yr:,.0f}, "
                    f"policy ${result.policy_opportunity_10yr:,.0f}"
                )
            )
