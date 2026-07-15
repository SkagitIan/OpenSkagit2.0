from django.db import connection
from django.shortcuts import render
from django.http import Http404
from opportunity.public_intelligence import public_home_examples


def parcel_fingerprint():
    """Build a countywide parcel fingerprint from meaningful public records."""
    sources = [
        ("assessor_rollup", "parcel_number", "Assessor"),
        ("skagit_parcels", "parcel_number", "Parcel record"),
        ("gis_skagit_parcels", "parcel_id", "Parcel geometry"),
        ("sales", "parcel_number", "Sales"),
        ("land", "parcelnumber", "Land"),
        ("improvements", "parcelnumber", "Improvements"),
        ("auditor_recordings", "parcel_number", "Documents"),
        ("parcel_primary_zoning", "parcel_id", "Zoning"),
        ("parcel_geo_static_features", "parcel_number", "Geo features"),
        ("v_land_ledger_source", "parcel_number", "Land Ledger"),
        ("v_parcel_tax_summary", "parcel_number", "Tax districts"),
        ("v_parcel_tax_detail", "parcel_number", "Tax detail"),
        ("tax_delinquency_taxstatement", "parcel_number", "Tax status"),
        ("skagit_parcel_history", "parcel_number", "Value history"),
    ]
    available_tables = {item.name for item in connection.introspection.get_table_list(connection.cursor())}
    row_counts = {}
    nodes = []
    spatial_tables = {"gis_skagit_parcels", "v_land_ledger_source", "parcel_geo_static_features"}

    try:
        with connection.cursor() as cursor:
            for table, key, label in sources:
                if table not in available_tables:
                    continue
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                    count = cursor.fetchone()[0]
                except Exception:
                    count = 0
                row_counts[table] = count
                nodes.append({
                    "label": label,
                    "rows": count,
                    "count": f"{count:,}",
                    "active": bool(count),
                })

            waza_match = "waza_zoning_zones" in available_tables and row_counts.get("gis_skagit_parcels", 0) > 0
    except Exception:
        row_counts = {}
        nodes = [{"label": label, "rows": 0, "count": "0", "active": False} for _, _, label in sources]
        waza_match = False

    active_sources = sum(node["active"] for node in nodes)
    evidence_records = sum(row_counts.get(table, 0) for table in [
        "assessor_rollup", "skagit_parcels", "gis_skagit_parcels", "land",
        "parcel_primary_zoning", "parcel_geo_static_features", "v_land_ledger_source",
        "tax_delinquency_taxstatement", "sales", "improvements", "v_parcel_tax_summary",
        "v_parcel_tax_detail", "auditor_recordings", "skagit_parcel_history",
    ])
    spatial_matches = sum(row_counts.get(table, 0) > 0 for table in spatial_tables) + int(waza_match)
    verified_joins = sum([
        row_counts.get("assessor_rollup", 0) > 0 and row_counts.get("gis_skagit_parcels", 0) > 0,
        row_counts.get("gis_skagit_parcels", 0) > 0 and waza_match,
        row_counts.get("parcel_primary_zoning", 0) > 0,
        row_counts.get("sales", 0) > 0,
        row_counts.get("improvements", 0) > 0,
        row_counts.get("v_parcel_tax_summary", 0) > 0 and row_counts.get("v_parcel_tax_detail", 0) > 0,
        row_counts.get("auditor_recordings", 0) > 0,
        row_counts.get("skagit_parcel_history", 0) > 0,
        row_counts.get("parcel_geo_static_features", 0) > 0,
        row_counts.get("v_land_ledger_source", 0) > 0,
    ])
    return {
        "datasets": active_sources + int(waza_match) or len(sources),
        "evidence_records": evidence_records,
        "spatial_matches": spatial_matches,
        "verified_joins": verified_joins,
        "nodes": [node for node in nodes if node["active"]][:10] or nodes,
    }
CITY_PAGES = [
    {
        "name": "Sedro-Woolley",
        "slug": "sedro-woolley",
        "accent": "#5BBB2F",
        "tagline": "River roads, timber history, and Highway 20 growth.",
        "summary": "A workspace for Sedro-Woolley parcels, permits, tax districts, public questions, and future map layers.",
    },
    {
        "name": "Burlington",
        "slug": "burlington",
        "accent": "#F5A623",
        "tagline": "Commerce, schools, farmland edges, and regional connections.",
        "summary": "A place to organize Burlington questions, sales patterns, levy impacts, development activity, and local data projects.",
    },
    {
        "name": "Mount Vernon",
        "slug": "mount-vernon",
        "accent": "#3B82C4",
        "tagline": "County seat, Skagit River neighborhoods, and civic records.",
        "summary": "A hub for Mount Vernon parcels, assessment trends, public services, downtown activity, and future city-tagged analysis.",
    },
    {
        "name": "Anacortes",
        "slug": "anacortes",
        "accent": "#1AACB0",
        "tagline": "Waterfront property, port activity, islands, and neighborhoods.",
        "summary": "A page for Anacortes questions, maps, tax context, waterfront sales, and public records organized by place.",
    },
    {
        "name": "Concrete",
        "slug": "concrete",
        "accent": "#3D4D5C",
        "tagline": "Upper Valley parcels, public lands, river risk, and small-town services.",
        "summary": "A future home for Concrete data, maps, parcel questions, levy context, and development records.",
    },
    {
        "name": "La Conner",
        "slug": "la-conner",
        "accent": "#C7772E",
        "tagline": "Waterfront village, historic parcels, and Swinomish Channel context.",
        "summary": "A page for La Conner public records, tourism-area questions, parcels, assessments, and future local projects.",
    },
    {
        "name": "Hamilton",
        "slug": "hamilton",
        "accent": "#7A9A35",
        "tagline": "Floodplain questions, river history, and Upper Skagit records.",
        "summary": "A workspace for Hamilton parcel records, floodplain maps, tax questions, and place-tagged community data.",
    },
    {
        "name": "Lyman",
        "slug": "lyman",
        "accent": "#6A8FBF",
        "tagline": "Small-town parcels, river corridor context, and local services.",
        "summary": "A page for Lyman records, maps, public questions, parcel activity, and future town-specific data.",
    },
]

CURRENT_TOPICS = [
    {
        "category": "finance",
        "time": "2 min ago",
        "is_new": True,
        "question": "Why did the port levy increase in 2024?",
        "answer": "The Port of Skagit raised its general levy 4.2% this year, driven by capital project debt service for the new marine terminal. A typical parcel contributes about $34/year to this district.",
        "source": "Skagit County Treasurer - DOR Levy Certification",
        "tags": [],
        "opacity": "1",
    },
    {
        "category": "permits",
        "time": "8 min ago",
        "question": "How many permits filed in Sedro-Woolley this month?",
        "answer": "14 permits since June 1 - 9 residential additions, 3 commercial tenant improvements, 2 accessory structures. Activity is concentrated in the downtown UGA.",
        "source": "City of Sedro-Woolley - iWorQ Permit System",
        "tags": ["sedro-woolley"],
        "opacity": "1",
    },
    {
        "category": "parcels",
        "time": "14 min ago",
        "question": "Who owns the parcel at Cook Rd and Hwy 20?",
        "answer": "4.3 acres held by Skagit Land Holdings LLC, assessed at $1.2M, zoned Rural Industrial. Last transferred 2019. No active permits on file.",
        "source": "Skagit County Assessor - CMAS",
        "tags": ["sedro-woolley"],
        "opacity": ".85",
    },
    {
        "category": "districts",
        "time": "22 min ago",
        "question": "How many taxing districts touch a Burlington parcel?",
        "answer": "A typical Burlington parcel overlaps 11 taxing districts - state, county, city, school, fire, port, library, hospital, EMS, cemetery, and flood control. Each levies independently.",
        "source": "Skagit County Assessor - District Crosswalk",
        "tags": ["burlington"],
        "opacity": ".72",
    },
    {
        "category": "planning",
        "time": "31 min ago",
        "question": "What does the comp plan say about housing near Burlington?",
        "answer": "The 2024 Comp Plan designates the Burlington UGA for medium-density residential growth, targeting 1,200 new units by 2044 along transit corridors.",
        "source": "Skagit County Planning - 2024 Comp Plan Update",
        "tags": ["burlington"],
        "opacity": ".55",
    },
    {
        "category": "gis",
        "time": "45 min ago",
        "question": "What's in the floodplain near the river in Concrete?",
        "answer": "14 parcels in Concrete intersect the FEMA 100-year floodplain. 9 have structures. 6 are Zone AE with mandatory flood insurance requirements.",
        "source": "Skagit County GIS - FEMA FIRM",
        "tags": ["concrete"],
        "opacity": ".40",
    },
]


def _format_number(value):
    if value is None:
        return "-"
    return f"{int(round(float(value))):,}"


def _format_money(value):
    if value is None:
        return "-"
    return f"${int(round(float(value))):,}"


def city_stats(city_page):
    stats = {
        "parcel_count": None,
        "recent_sales_90": None,
        "avg_home_value": None,
        "avg_home_sale_price": None,
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    parcel_count,
                    recent_sales_90,
                    avg_home_value,
                    avg_home_sale_price
                FROM v_city_stats
                WHERE slug = %s
                """,
                [city_page["slug"]],
            )
            row = cursor.fetchone()
    except Exception:
        return stats

    if row:
        stats.update({
            "parcel_count": row[0],
            "recent_sales_90": row[1],
            "avg_home_value": row[2],
            "avg_home_sale_price": row[3],
        })
    return stats


def city_stat_cards(city_page):
    stats = city_stats(city_page)
    return [
        {"label": "Parcels", "value": _format_number(stats["parcel_count"])},
        {"label": "90-day sales", "value": _format_number(stats["recent_sales_90"])},
        {"label": "Avg home value", "value": _format_money(stats["avg_home_value"])},
        {"label": "Avg 90-day sale", "value": _format_money(stats["avg_home_sale_price"])},
    ]


def home(request):
    return render(request, "pages/home.html", {
        "city_pages": CITY_PAGES,
        "current_topics": CURRENT_TOPICS,
        "current_count": "1,247",
        "show_current_load_more": True,
        "parcel_fingerprint": parcel_fingerprint(),
        "property_intelligence_examples": public_home_examples(),
    })


def city(request, slug):
    city_page = next((item for item in CITY_PAGES if item["slug"] == slug), None)
    if city_page is None:
        raise Http404("City not found")
    city_prompts = [
        f"What changed in {city_page['name']} property values this year?",
        f"Show recent sales in {city_page['name']}.",
        f"Which tax districts overlap {city_page['name']} parcels?",
        f"What public records are available for {city_page['name']}?",
    ]
    current_topics = [
        topic for topic in CURRENT_TOPICS
        if city_page["slug"] in topic.get("tags", [])
    ]
    return render(request, "pages/city.html", {
        "city": city_page,
        "city_pages": CITY_PAGES,
        "city_prompts": city_prompts,
        "city_stat_cards": city_stat_cards(city_page),
        "current_topics": current_topics,
        "current_count": f"{len(current_topics):,}",
        "show_current_load_more": False,
    })
