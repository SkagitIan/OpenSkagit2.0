"""
export_geo_features_parquet -- export parcel_geo_static_features to Parquet.

Writes the entire table (all statuses) to
data/processed/parcel_geo_static_features.parquet so other tools can consume
it without a database connection.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from assessor_sync.models import ParcelGeoStaticFeature

DEFAULT_RELATIVE_PATH = Path("data") / "processed" / "parcel_geo_static_features.parquet"


class Command(BaseCommand):
    help = "Export parcel_geo_static_features to a Parquet file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(Path(settings.BASE_DIR) / DEFAULT_RELATIVE_PATH),
            help="Destination .parquet path.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows = list(ParcelGeoStaticFeature.objects.all().values())
        frame = pd.DataFrame(rows)
        frame.to_parquet(output_path, index=False)

        self.stdout.write(f"Exported {len(frame):,} rows to {output_path}")
