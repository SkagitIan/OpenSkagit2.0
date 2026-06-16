from django.shortcuts import render
from django.http import Http404, HttpResponseNotAllowed
from django.urls import reverse
from django.utils.http import urlencode
from django.shortcuts import redirect

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


def home(request):
    return render(request, "pages/home.html", {"city_pages": CITY_PAGES})


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
    return render(request, "pages/city.html", {
        "city": city_page,
        "city_pages": CITY_PAGES,
        "city_prompts": city_prompts,
    })


def app(request):
    prompt = request.GET.get("prompt", request.GET.get("q", "")).strip()
    url = reverse("ask")
    if prompt:
        url = f"{url}?{urlencode({'prompt': prompt})}"
    return redirect(url)


def ask(request):
    answer = None
    analysis = None
    result = None
    sql = ""
    prompt = request.GET.get("prompt", "").strip()
    error = None

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        if prompt:
            from .agent import answer_question
            analysis = answer_question(prompt)
            answer = analysis.answer
            result = analysis.result
            sql = analysis.sql or ""

    return render(request, "pages/ask.html", {
        "answer": answer,
        "analysis": analysis,
        "result": result,
        "sql": sql,
        "prompt": prompt,
        "error": error,
        "starter_prompts": STARTER_PROMPTS,
        "city_pages": CITY_PAGES,
    })


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
