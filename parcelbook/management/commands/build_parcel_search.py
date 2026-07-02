from django.core.management.base import BaseCommand

from parcelbook.data.parcel_search_builder import OpenSkagitParcelSearchBuilder


class Command(BaseCommand):
    help = "Rebuild ParcelBook derived parquet outputs in R2."

    def handle(self, *args, **options):
        results = OpenSkagitParcelSearchBuilder.from_env().run_all()
        for name, df in results.items():
            self.stdout.write(self.style.SUCCESS(name))
            self.stdout.write(df.to_string(index=False))
