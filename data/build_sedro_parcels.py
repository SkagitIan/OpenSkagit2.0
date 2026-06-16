"""
build_sedro_parcels.py
=======================
One-shot data prep for the Sedro-Woolley "Land Ledger" parcel scenario map.

Reads the Skagit County parcel boundary shapefile (data/parcels-shp.zip,
already unzipped into data/parcels-shp/), reprojects geometry from
WA State Plane North (EPSG:2926, feet) to WGS84 lon/lat, and joins it
against skagit_parcels + the tax breakdown views for parcels inside the
Sedro-Woolley city limits (city_district = 'Sedro Woolley').

Computes, per land-use scenario category, the citywide median tax/acre,
then writes a single GeoJSON FeatureCollection (with an extra top-level
"metadata" key carrying the scenario medians and the citywide headline
number) to static/data/sedro_woolley_parcels.geojson.

Run from project root:
    python data/build_sedro_parcels.py
"""

import json
import os
import statistics
from pathlib import Path

import psycopg
import shapefile
from pyproj import Transformer

BASE_DIR = Path(__file__).resolve().parent.parent
SHP_PATH = BASE_DIR / "data" / "parcels-shp" / "Parcels.shp"
OUT_PATH = BASE_DIR / "static" / "data" / "sedro_woolley_parcels.geojson"

CITY_MCAG = "0647"
BUILDOUT_FACTOR = 0.5
HORIZON_YEARS = 10

# land_use codes -> scenario category, keyed by the leading numeric code
SFR_CODES = {"110", "111", "112", "113", "180", "181", "182", "185"}
MULTI_CODES = {"120", "130", "140", "150"}
RETAIL_CODES = {"510", "520", "530", "540", "550", "560", "580", "590",
                 "610", "620", "640", "650", "660", "690"}
VACANT_CODES = {"910", "911", "912", "940", "941"}


def category_for(land_use):
    if not land_use:
        return "other"
    code = land_use.strip().lstrip("(").split(")")[0].strip()
    if code in SFR_CODES:
        return "sfr"
    if code in MULTI_CODES:
        return "multi"
    if code in RETAIL_CODES:
        return "retail"
    if code in VACANT_CODES:
        return "vacant"
    return "other"


def group_for(land_use):
    """Broad filter bucket: residential / commercial / industrial / vacant_other."""
    if not land_use:
        return "vacant_other"
    code = land_use.strip().lstrip("(").split(")")[0].strip()
    if not code.isdigit():
        return "vacant_other"
    code_int = int(code)
    if 100 <= code_int < 200:
        return "residential"
    if 500 <= code_int < 700:
        return "commercial"
    if 200 <= code_int < 500:
        return "industrial"
    return "vacant_other"


def load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def fetch_parcel_rows(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT parcel_number, situs_street_number, situs_street_name,
               acres, land_use, total_taxes, assessed_value
        FROM skagit_parcels
        WHERE city_district = 'Sedro Woolley'
          AND inactive_date IS NULL
          AND acres IS NOT NULL AND acres > 0
          AND total_taxes IS NOT NULL
    """)
    cols = [d.name for d in cur.description]
    rows = {}
    for rec in cur.fetchall():
        row = dict(zip(cols, rec))
        rows[row["parcel_number"]] = row
    return rows


def fetch_city_share(conn, parcel_numbers):
    """Per-parcel fraction of the tax bill that goes to the City of Sedro-Woolley."""
    cur = conn.cursor()
    cur.execute("""
        SELECT parcel_number, SUM(total_tax) AS city_tax
        FROM v_parcel_tax_summary
        WHERE mcag = %s
        GROUP BY parcel_number
    """, (CITY_MCAG,))
    city_tax = {r[0]: float(r[1]) for r in cur.fetchall()}

    cur.execute("""
        SELECT parcel_number, SUM(total_tax) AS total_tax
        FROM v_parcel_tax_summary
        GROUP BY parcel_number
    """)
    total_tax = {r[0]: float(r[1]) for r in cur.fetchall() if r[0] in parcel_numbers}

    share = {}
    for pnum in parcel_numbers:
        t = total_tax.get(pnum, 0.0)
        c = city_tax.get(pnum, 0.0)
        share[pnum] = (c / t) if t > 0 else 0.0
    return share


def load_geometries():
    sf = shapefile.Reader(str(SHP_PATH))
    transformer = Transformer.from_crs("EPSG:2926", "EPSG:4326", always_xy=True)

    def reproject(coords):
        if isinstance(coords[0], (int, float)):
            x, y = transformer.transform(coords[0], coords[1])
            return [round(x, 7), round(y, 7)]
        return [reproject(c) for c in coords]

    geoms = {}
    for sr in sf.iterShapeRecords():
        pid = sr.record["PARCELID"]
        if not pid:
            continue
        gi = sr.shape.__geo_interface__
        gi = {"type": gi["type"], "coordinates": reproject(gi["coordinates"])}
        geoms[pid] = gi
    return geoms


def median_tax_per_acre(parcels, category):
    vals = [p["tax_per_acre"] for p in parcels.values() if p["category"] == category]
    if not vals:
        return None
    return statistics.median(vals)


def main():
    load_env()
    database_url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    conn = psycopg.connect(database_url)

    print("Loading parcel attributes from skagit_parcels...")
    rows = fetch_parcel_rows(conn)
    print(f"  {len(rows)} active Sedro-Woolley parcels with acres > 0")

    print("Loading per-parcel city tax share...")
    city_share = fetch_city_share(conn, set(rows.keys()))

    print("Loading parcel geometry from shapefile...")
    geoms = load_geometries()

    parcels = {}
    for pnum, row in rows.items():
        geom = geoms.get(pnum)
        if geom is None:
            continue
        acres = float(row["acres"])
        total_tax = float(row["total_taxes"])
        tax_per_acre = total_tax / acres
        category = category_for(row["land_use"])
        street = " ".join(
            s for s in [row["situs_street_number"], row["situs_street_name"]] if s
        ).strip()
        parcels[pnum] = {
            "parcel_number": pnum,
            "address": street or None,
            "acres": round(acres, 3),
            "land_use": (row["land_use"] or "").strip(),
            "category": category,
            "land_use_group": group_for(row["land_use"]),
            "current_tax": round(total_tax, 2),
            "tax_per_acre": round(tax_per_acre, 2),
            "city_tax_pct": round(city_share.get(pnum, 0.0) * 100, 2),
            "geometry": geom,
        }

    print(f"  {len(parcels)} parcels matched to geometry")

    sfr_median = median_tax_per_acre(parcels, "sfr")
    multi_median = median_tax_per_acre(parcels, "multi")
    retail_median = median_tax_per_acre(parcels, "retail")

    scenarios = {
        "small_infill": {
            "label": "Small Infill",
            "tax_per_acre": round(sfr_median, 2),
        },
        "townhomes": {
            "label": "Townhomes",
            "tax_per_acre": round(multi_median * 0.75, 2),
        },
        "small_multifamily": {
            "label": "Small Multifamily",
            "tax_per_acre": round(multi_median, 2),
        },
        "mixed_use": {
            "label": "Mixed-Use",
            "tax_per_acre": round((retail_median + multi_median) / 2, 2),
        },
    }
    print("Scenario medians (tax/acre):")
    for key, s in scenarios.items():
        print(f"  {s['label']:20s} ${s['tax_per_acre']:,.0f}")

    citywide_opportunity = 0.0
    for p in parcels.values():
        best_gain_per_acre = max(
            s["tax_per_acre"] - p["tax_per_acre"] for s in scenarios.values()
        )
        if best_gain_per_acre > 0:
            annual_gain = best_gain_per_acre * p["acres"]
            citywide_opportunity += annual_gain * HORIZON_YEARS * BUILDOUT_FACTOR

    print(f"Citywide 10-year modeled opportunity: ${citywide_opportunity:,.0f}")

    features = []
    for p in parcels.values():
        geom = p.pop("geometry")
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": p,
        })

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "city": "Sedro-Woolley",
            "scenarios": scenarios,
            "buildout_factor": BUILDOUT_FACTOR,
            "horizon_years": HORIZON_YEARS,
            "citywide_opportunity_10yr": round(citywide_opportunity, 2),
            "parcel_count": len(features),
        },
        "features": features,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(geojson))
    print(f"Wrote {len(features)} features -> {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
