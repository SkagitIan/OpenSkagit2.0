import re

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

DISSOLVE_SQL = """
SELECT sp.levy_code,
       count(*) AS parcel_count,
       PERCENTILE_CONT(0.5) WITHIN GROUP (
           ORDER BY sp.total_taxes / NULLIF(sp.assessed_value, 0) * 1000
       ) AS median_rate,
       mode() WITHIN GROUP (ORDER BY sp.situs_city_state_zip) AS modal_situs,
       ST_Multi(ST_SimplifyPreserveTopology(ST_Union(gsp.geometry), 0.00003)) AS geometry
FROM skagit_parcels sp
JOIN gis_skagit_parcels gsp
  ON upper(trim(gsp.parcel_id)) = upper(trim(sp.parcel_number))
WHERE sp.inactive_date IS NULL
  AND sp.levy_code IS NOT NULL
  AND sp.total_taxes IS NOT NULL AND sp.total_taxes > 0
  AND sp.assessed_value IS NOT NULL AND sp.assessed_value > 0
  AND gsp.geometry IS NOT NULL
GROUP BY sp.levy_code
"""


def area_label_from_situs(modal_situs, levy_code):
    if not modal_situs:
        return levy_code
    city = modal_situs.split(",")[0].strip()
    if not city:
        return levy_code
    return re.sub(r"\s+", " ", city).title()


class Command(BaseCommand):
    help = "Rebuild the precomputed levy_area_map table (dissolved levy-code area geometry + median effective rate)."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(DISSOLVE_SQL)
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            rebuilt_at = timezone.now()
            cursor.execute("DELETE FROM levy_area_map")
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO levy_area_map
                        (levy_code, area_label, parcel_count, median_rate, geometry, rebuilt_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (levy_code) DO UPDATE SET
                        area_label = EXCLUDED.area_label,
                        parcel_count = EXCLUDED.parcel_count,
                        median_rate = EXCLUDED.median_rate,
                        geometry = EXCLUDED.geometry,
                        rebuilt_at = EXCLUDED.rebuilt_at
                    """,
                    [
                        row["levy_code"],
                        area_label_from_situs(row["modal_situs"], row["levy_code"]),
                        row["parcel_count"],
                        row["median_rate"],
                        row["geometry"],
                        rebuilt_at,
                    ],
                )

        if rows:
            rates = [float(row["median_rate"]) for row in rows if row["median_rate"] is not None]
            self.stdout.write(
                self.style.SUCCESS(
                    f"Rebuilt levy_area_map: {len(rows)} areas, "
                    f"{sum(row['parcel_count'] for row in rows):,} parcels, "
                    f"median_rate range ${min(rates):.2f}-${max(rates):.2f} per $1,000"
                )
            )
        else:
            self.stdout.write(self.style.WARNING("Rebuilt levy_area_map: 0 areas found."))
