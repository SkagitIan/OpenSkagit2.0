import json

from django.db import connection
from django.shortcuts import render
from django.http import Http404, HttpResponseNotAllowed, JsonResponse, StreamingHttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlencode
from django.shortcuts import redirect

from .land_ledger import CITY_CONFIGS

STARTER_PROMPTS = [
    "How many parcels are in each city?",
    "What are the largest parcels by acreage in Mount Vernon?",
    "Show recent sales by neighborhood with median price",
    "Which land use codes are most common?",
    "Parcels over 10 acres with public utilities",
    "IAAO sales ratio check for residential properties",
]

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


def _json_value(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool, list, dict)):
        return value
    return float(value)


LAND_LEDGER_JSON_FIELDS = {
    "allowed_scenarios",
    "policy_scenarios",
    "scenario_results",
    "benchmark_source",
    "exclusion_reasons",
    "model_flags",
    "diagnostics",
    "scenario_definitions",
    "zone_descriptions",
    "scenario_totals",
    "exclusion_counts",
}


def _land_ledger_value(key, value):
    if key in LAND_LEDGER_JSON_FIELDS and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return _json_value(value)


def land_ledger_summary(request, city_slug):
    if city_slug not in CITY_CONFIGS:
        raise Http404("City not found")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT city_slug, city_name, parcel_count, zoned_count,
                   unknown_zone_count, current_opportunity_10yr,
                   policy_opportunity_10yr, city_current_opportunity_10yr,
                   city_policy_opportunity_10yr, eligible_parcel_count,
                   excluded_parcel_count, scenario_totals, exclusion_counts,
                   assumption_version, diagnostics, scenario_definitions,
                   zone_descriptions, buildout_factor, horizon_years, rebuilt_at
            FROM land_ledger_city_summary
            WHERE city_slug = %s
            """,
            [city_slug],
        )
        row = cursor.fetchone()
        if row is None:
            return JsonResponse({
                "city_slug": city_slug,
                "city_name": CITY_CONFIGS[city_slug]["name"],
                "ready": False,
                "message": "Land Ledger has not been rebuilt for this city yet.",
            }, status=404)
        cols = [col[0] for col in cursor.description]
    payload = {key: _land_ledger_value(key, value) for key, value in zip(cols, row)}
    payload["ready"] = True
    return JsonResponse(payload)


def land_ledger_parcels(request, city_slug):
    if city_slug not in CITY_CONFIGS:
        raise Http404("City not found")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                parcel_number, address, acres, land_use, category, zone_id,
                zone_name, zone_group, current_tax, tax_per_acre, city_tax_pct,
                productivity_percentile, productivity_label, allowed_scenarios,
                policy_scenarios, scenario_results, current_opportunity_10yr,
                policy_opportunity_10yr, city_current_opportunity_10yr,
                city_policy_opportunity_10yr, exclusion_reasons, model_flags,
                assumption_version,
                benchmark_source, ST_AsGeoJSON(geometry, 7)::json AS geometry
            FROM land_ledger_parcels
            WHERE city_slug = %s
              AND geometry IS NOT NULL
            """,
            [city_slug],
        )
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

    features = []
    for row in rows:
        geometry = row.pop("geometry")
        properties = {key: _land_ledger_value(key, value) for key, value in row.items()}
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": properties,
        })
    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })


def app(request):
    prompt = request.GET.get("prompt", request.GET.get("q", "")).strip()
    url = reverse("ask")
    if prompt:
        url = f"{url}?{urlencode({'prompt': prompt})}"
    return redirect(url)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def ask_stream(request):
    prompt = request.GET.get("prompt", "").strip()

    def events():
        if not prompt:
            html = render_to_string("partials/ask_messages.html", {"error": "Please enter a question."})
            yield _sse("answer", {"html": html})
            yield _sse("done", {})
            return

        yield _sse("status", {"message": "thinking"})
        yield _sse("status", {"message": "querying"})
        yield _sse("status", {"message": "summarizing"})

        from .agent import answer_question

        analysis = answer_question(prompt)
        html = render_to_string("partials/ask_messages.html", {
            "answer": analysis.answer,
            "analysis": analysis,
            "result": analysis.result,
            "sql": analysis.sql or "",
        })
        yield _sse("answer", {"html": html})
        yield _sse("done", {})

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def ask(request):
    answer = None
    analysis = None
    result = None
    sql = ""
    prompt = ""
    composer_prompt = request.GET.get("prompt", "").strip()
    error = None

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        composer_prompt = ""
        if prompt:
            from .agent import answer_question
            analysis = answer_question(prompt)
            answer = analysis.answer
            result = analysis.result
            sql = analysis.sql or ""

    context = {
        "answer": answer,
        "analysis": analysis,
        "result": result,
        "sql": sql,
        "prompt": prompt,
        "composer_prompt": composer_prompt,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
        "city_pages": CITY_PAGES,
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "partials/ask_messages.html", context)

    return render(request, "pages/ask.html", context)


def ask_sql(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    sql = request.POST.get("sql", "").strip()
    prompt = request.POST.get("prompt", "").strip()
    result = None
    error = None

    if sql:
        from .agent import execute_analysis_sql
        try:
            result = execute_analysis_sql(sql)
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

    return render(request, "pages/ask.html", {
        "sql": sql,
        "prompt": prompt,
        "result": result,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
        "city_pages": CITY_PAGES,
    })
