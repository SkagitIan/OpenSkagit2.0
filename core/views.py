from django.db import connection
from django.shortcuts import render
from django.http import Http404


FINGERPRINT_PARCEL = "P96023"


def parcel_fingerprint(parcel_number=FINGERPRINT_PARCEL):
    """Build a parcel fingerprint from actual keyed and spatial relationships."""
    sources = [
        ("assessor_rollup", "parcel_number", "Assessor"),
        ("skagit_parcels", "parcel_number", "Parcel record"),
        ("gis_skagit_parcels", "parcel_id", "Parcel geometry"),
        ("sales", "parcel_number", "Sales"),
        ("land", "parcelnumber", "Land segments"),
        ("parcel_primary_zoning", "parcel_id", "Zoning"),
        ("parcel_zoning", "parcel_id", "Zoning overlaps"),
        ("parcel_geo_static_features", "parcel_number", "Geo features"),
        ("v_land_ledger_source", "parcel_number", "Land Ledger source"),
        ("v_parcel_tax_summary", "parcel_number", "Tax districts"),
        ("v_parcel_tax_detail", "parcel_number", "Tax detail"),
        ("skagit_levy_composition", "levy_code", "Levy lines"),
        ("tax_delinquency_taxstatement", "parcel_number", "Tax status"),
        ("skagit_parcel_history", "parcel_number", "Value history"),
    ]
    spatial_tables = {"gis_skagit_parcels", "v_land_ledger_source", "parcel_geo_static_features"}
    available_tables = {item.name for item in connection.introspection.get_table_list(connection.cursor())}
    nodes = []
    total_points = 0

    try:
        with connection.cursor() as cursor:
            levy_code = None
            tax_year = None
            cursor.execute(
                'SELECT levy_code, tax_year FROM "skagit_parcels" WHERE "parcel_number" = %s',
                [parcel_number],
            )
            parcel_row = cursor.fetchone()
            if parcel_row:
                levy_code, tax_year = parcel_row

            for table, key, label in sources:
                if table not in available_tables:
                    continue
                filter_value = parcel_number
                filter_sql = f'"{key}" = %s'
                params = [filter_value]
                if table == "skagit_levy_composition":
                    filter_sql = '"levy_code" = %s AND "tax_year" = %s'
                    params = [levy_code, tax_year]
                try:
                    columns = [field.name for field in connection.introspection.get_table_description(cursor, table)]
                    cursor.execute(f'SELECT * FROM "{table}" WHERE {filter_sql}', params)
                    rows = cursor.fetchall()
                    field_count = sum(
                        sum(value not in (None, "") for column, value in zip(columns, row)
                            if column not in {"id", "raw_data", "raw_row", "geometry"})
                        for row in rows
                    )
                    total_points += field_count
                    nodes.append({"label": label, "rows": len(rows), "points": field_count, "active": bool(rows)})
                except Exception:
                    nodes.append({"label": label, "rows": 0, "points": 0, "active": False})

            cursor.execute(
                'SELECT COUNT(*) FROM "waza_zoning_zones" z '
                'JOIN "gis_skagit_parcels" g ON ST_Intersects(z.geometry, g.geometry) '
                'WHERE g.parcel_id = %s',
                [parcel_number],
            )
            waza_match = cursor.fetchone()[0] > 0
    except Exception:
        nodes = [{"label": label, "rows": 0, "points": 0, "active": False} for _, _, label in sources]
        waza_match = False

    active_sources = sum(node["active"] for node in nodes)
    spatial_matches = sum(node["active"] for node, (table, _, _) in zip(nodes, sources) if table in spatial_tables)
    spatial_matches += int(waza_match)
    relationships = sum([
        any(node["active"] for node in nodes if node["label"] == "Parcel geometry") and waza_match,
        any(node["active"] for node in nodes if node["label"] == "Zoning overlaps") and waza_match,
        any(node["active"] for node in nodes if node["label"] == "Tax districts"),
        any(node["active"] for node in nodes if node["label"] == "Value history"),
        any(node["active"] for node in nodes if node["label"] == "Geo features"),
        any(node["active"] for node in nodes if node["label"] == "Land Ledger source"),
        any(node["active"] for node in nodes if node["label"] == "Sales"),
    ])
    display_nodes = [node for node in nodes if node["active"]][:10] or nodes
    return {
        "parcel_number": parcel_number,
        "datasets": active_sources or len(sources),
        "data_points": total_points,
        "spatial_matches": spatial_matches,
        "hidden_relationships": relationships,
        "nodes": display_nodes,
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
