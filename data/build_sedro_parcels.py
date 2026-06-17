"""
build_sedro_parcels.py
=======================
One-shot data prep for the Sedro-Woolley "Land Ledger" parcel scenario map.

Reads the Skagit County parcel boundary shapefile (data/parcels-shp.zip,
already unzipped into data/parcels-shp/), reprojects geometry from
WA State Plane North (EPSG:2926, feet) to WGS84 lon/lat, and joins it
against skagit_parcels + the tax breakdown views + parcel_primary_zoning
for parcels inside the Sedro-Woolley city limits.

Scenarios are now filtered by what each parcel's zoning district actually
permits (Title 17 SWMC) rather than by assessor land-use codes.

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

# Which scenario keys are legally plausible per zone (Title 17 SWMC).
# Scenarios not in a zone's list are hidden in the UI for that parcel.
ZONE_SCENARIOS = {
    "R-1":  ["small_infill"],
    "R-5":  ["small_infill"],
    "R-7":  ["small_infill", "townhomes"],
    "R-15": ["small_infill", "townhomes"],
    "CBD":  ["small_multifamily", "mixed_use"],
    "MC":   ["townhomes", "small_multifamily", "mixed_use"],
    "I":    ["mixed_use"],
    "P":    [],
    "OS":   [],
}

# Natural-language zone descriptions grounded in Title 17 SWMC intent language.
ZONE_DESCRIPTIONS = {
    "R-1": {
        "label": "Residential 1 — Environmentally Constrained",
        "description": (
            "Low-density single-family areas within or adjacent to environmentally "
            "sensitive land — wetlands, steep slopes, floodplains, or similar critical "
            "areas. Development is limited to protect these natural systems. Large lots, "
            "no multifamily, no subdivision to urban densities. The ceiling here is set "
            "by ecology, not just policy."
        ),
    },
    "R-5": {
        "label": "Residential 5",
        "description": (
            "Single-family neighborhoods on the city's edges where terrain is rolling "
            "or land transitions to the surrounding rural county. Minimum 5,000 sq ft "
            "lots. New homes and accessory dwelling units are the primary uses. "
            "Not designed for multifamily apartment buildings."
        ),
    },
    "R-7": {
        "label": "Residential 7 — Historic Grid Neighborhoods",
        "description": (
            "The historic, walkable core of Sedro-Woolley — the grid-street blocks "
            "platted over a century ago with 7,000 sq ft lots. The code's explicit "
            "intent is to 'encourage continuation of this traditional pattern.' Houses "
            "sit close to the street. Duplexes and accessory dwelling units are "
            "typically permitted. Most amenable to gentle infill while keeping "
            "neighborhood character intact."
        ),
    },
    "R-15": {
        "label": "Residential 15",
        "description": (
            "Newer residential areas with larger 15,000 sq ft lots. The code requires "
            "grid-style streets (not cul-de-sacs), conventional neighborhood scale, and "
            "buildings that match the look of existing houses. Intended to avoid large "
            "apartment blocks disconnected from the rest of the community. Townhomes "
            "may be permitted; large apartment complexes are not."
        ),
    },
    "CBD": {
        "label": "Central Business District",
        "description": (
            "Downtown Sedro-Woolley — the commercial and civic core along Woodworth "
            "and Metcalf Streets. Ground-floor retail, restaurants, offices, and "
            "services are primary uses; residential above commercial is encouraged. "
            "Buildings are expected at or near the sidewalk. The highest allowable "
            "density and widest mix of uses in the city."
        ),
    },
    "MC": {
        "label": "Mixed Commercial",
        "description": (
            "Commercial corridors at the city's entrances and along major roads — "
            "particularly the Highway 20 and Cook Road corridors. The code's intent is "
            "an 'attractive and welcoming appearance to visitors,' managing traffic, and "
            "encouraging walking alongside commercial activity. Both commercial uses and "
            "residential uses (apartments, mixed-use buildings) are permitted."
        ),
    },
    "I": {
        "label": "Industrial",
        "description": (
            "Lands set aside for manufacturing, warehousing, distribution, and business "
            "park uses to 'enhance the city's economic base in a manner that minimizes "
            "impacts to surrounding nonindustrial zones.' Commercial and residential "
            "uses are permitted only at limited scale so the majority of this land "
            "stays available for job-producing industrial development."
        ),
    },
    "P": {
        "label": "Public",
        "description": (
            "Land owned or reserved for civic, governmental, educational, utility, or "
            "institutional purposes — schools, city hall, fire stations, wastewater "
            "treatment, and similar facilities. Private development is generally not "
            "permitted. These parcels represent stable, non-developable baseline land."
        ),
    },
    "OS": {
        "label": "Open Space",
        "description": (
            "Parks, natural areas, and protected open land. Development is not "
            "permitted. These parcels contribute green infrastructure and stormwater "
            "management but generate minimal property tax revenue by design."
        ),
    },
}


def zone_group_for(zone_id):
    """Broad filter bucket derived from zone code (used in place of assessor group)."""
    if not zone_id:
        return "other"
    z = zone_id.upper().strip()
    if z in ("R-1", "R-5", "R-7", "R-15") or z.startswith("R-") or "RESIDENTIAL" in z:
        return "residential"
    if z in ("CBD", "MC") or "COMMERCIAL" in z or "BUSINESS" in z:
        return "commercial"
    if z == "I" or "INDUSTRIAL" in z:
        return "industrial"
    if z in ("P", "OS") or "PUBLIC" in z or "OPEN" in z or "PARK" in z:
        return "public"
    return "other"


# Legacy assessor-code helpers kept for the category field (used in median calc).
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


def load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def connect():
    """Connect using NEW_DATABASE_URL if set, otherwise DATABASE_URL."""
    url = os.environ.get("NEW_DATABASE_URL") or os.environ["DATABASE_URL"]
    return psycopg.connect(url.replace("postgres://", "postgresql://", 1))


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


def fetch_zoning(conn):
    """Return {parcel_id: {zone_id, zone_name, waza_general}} from parcel_primary_zoning."""
    cur = conn.cursor()
    cur.execute("""
        SELECT parcel_id, zone_id, zone_name, waza_general
        FROM parcel_primary_zoning
        WHERE citydistrict ILIKE '%Sedro%'
    """)
    return {
        r[0]: {"zone_id": r[1], "zone_name": r[2], "waza_general": r[3]}
        for r in cur.fetchall()
    }


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
    conn = connect()

    print("Loading parcel attributes from skagit_parcels...")
    rows = fetch_parcel_rows(conn)
    print(f"  {len(rows)} active Sedro-Woolley parcels with acres > 0")

    print("Loading per-parcel city tax share...")
    city_share = fetch_city_share(conn, set(rows.keys()))

    print("Loading zoning from parcel_primary_zoning...")
    zoning = fetch_zoning(conn)
    print(f"  {len(zoning)} parcels with zone data")

    print("Loading parcel geometry from shapefile...")
    geoms = load_geometries()

    parcels = {}
    unzoned = 0
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
        z = zoning.get(pnum) or {}
        zone_id = z.get("zone_id") or None
        zone_name = z.get("zone_name") or None
        if not zone_id:
            unzoned += 1
        parcels[pnum] = {
            "parcel_number": pnum,
            "address": street or None,
            "acres": round(acres, 3),
            "land_use": (row["land_use"] or "").strip(),
            "category": category,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "zone_group": zone_group_for(zone_id),
            "current_tax": round(total_tax, 2),
            "tax_per_acre": round(tax_per_acre, 2),
            "city_tax_pct": round(city_share.get(pnum, 0.0) * 100, 2),
            "geometry": geom,
        }
    print(f"  {unzoned} parcels had no zone match")

    print(f"  {len(parcels)} parcels matched to geometry")

    sfr_median = median_tax_per_acre(parcels, "sfr")
    multi_median = median_tax_per_acre(parcels, "multi")
    retail_median = median_tax_per_acre(parcels, "retail")

    scenarios = {
        "small_infill": {
            "label": "Add a Home",
            "description": "One new single-family home, like the houses already on most Sedro-Woolley blocks.",
            "tax_per_acre": round(sfr_median, 2),
        },
        "townhomes": {
            "label": "Townhomes",
            "description": "A few attached homes sharing walls, each with its own entrance — less dense than an apartment building.",
            "tax_per_acre": round(multi_median * 0.75, 2),
        },
        "small_multifamily": {
            "label": "Small Apartment Building",
            "description": "A small multifamily building such as a fourplex or a small apartment complex.",
            "tax_per_acre": round(multi_median, 2),
        },
        "mixed_use": {
            "label": "Shops + Apartments",
            "description": "Ground-floor shops or offices with apartments above — sometimes called mixed-use.",
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
            "zone_scenarios": ZONE_SCENARIOS,
            "zone_descriptions": ZONE_DESCRIPTIONS,
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
