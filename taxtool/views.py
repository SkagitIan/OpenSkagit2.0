from django.shortcuts import render

from core.views import CITY_PAGES

from .queries import (
    search_parcels,
    get_parcel,
    get_tax_summary,
    get_levy_code_median,
    get_county_median,
    get_agency_crosswalk,
    get_county_total_for_mcag,
)
from .utils import (
    group_levy_rows,
    format_currency,
    format_amount_short,
    get_agency_color,
    get_agency_info,
)


def tax_home(request):
    return render(request, "taxtool/base.html", {"city_pages": CITY_PAGES})


def tax_search(request):
    q = request.GET.get("q", "").strip()
    parcels = search_parcels(q) if len(q) >= 2 else []
    return render(request, "taxtool/_suggestions.html", {"parcels": parcels, "q": q})


def tax_parcel(request, parcel_number):
    parcel = get_parcel(parcel_number)
    if not parcel:
        return render(request, "taxtool/_bill.html", {"error": "Parcel not found.", "parcel_number": parcel_number})

    summary_rows = get_tax_summary(parcel_number)
    grouped = group_levy_rows(summary_rows)

    # Attach color to each group from agency JSON type field
    for group in grouped:
        info = get_agency_info(group.get("mcag"))
        agency_type = info.get("type", "other") if info else "other"
        if group["key"] == "__STATE__":
            agency_type = "state"
        elif group["key"] == "__OTHER__":
            agency_type = "other"
        group["color"] = get_agency_color(agency_type)
        group["total_fmt"] = format_currency(group["total"])
        group["pct_fmt"] = f"{group['pct']}%"

    levy_code_median = get_levy_code_median(parcel.get("levy_code"))
    county_median = get_county_median()

    return render(request, "taxtool/_bill.html", {
        "parcel": parcel,
        "grouped": grouped,
        "total_fmt": format_currency(parcel.get("total_taxes")),
        "levy_code_median_fmt": format_currency(levy_code_median) if levy_code_median else None,
        "county_median_fmt": format_currency(county_median) if county_median else None,
    })


def tax_agency(request, mcag):
    # Pull user's tax amount for this agency from query param (passed by template)
    your_amount_raw = request.GET.get("your_amount")
    your_amount_fmt = format_currency(your_amount_raw) if your_amount_raw else None

    info = get_agency_info(mcag)
    crosswalk = get_agency_crosswalk(mcag)

    if not info and not crosswalk:
        return render(request, "taxtool/_agency.html", {
            "error": f"No data found for agency {mcag}.",
            "mcag": mcag,
        })

    common_name = (info or {}).get("common_name") or (crosswalk or {}).get("sao_legal_name", "Unknown Agency")
    blurb = (info or {}).get("blurb")
    budget = (info or {}).get("budget")
    sao_fit_url = (info or {}).get("sao_fit_url") or (crosswalk or {}).get("sao_fit_url")
    data_year = (info or {}).get("data_year")

    county_total = get_county_total_for_mcag(mcag)
    county_total_fmt = format_currency(county_total)

    top_expenditures = []
    if budget:
        top_expenditures = (budget.get("top_expenditures") or [])[:3]
        for exp in top_expenditures:
            exp["amount_fmt"] = format_amount_short(exp.get("amount"))

    return render(request, "taxtool/_agency.html", {
        "mcag": mcag,
        "common_name": common_name,
        "blurb": blurb,
        "budget": budget,
        "sao_fit_url": sao_fit_url,
        "data_year": data_year,
        "county_total_fmt": county_total_fmt,
        "your_amount_fmt": your_amount_fmt,
        "top_expenditures": top_expenditures,
        "revenue_fmt": format_amount_short((budget or {}).get("total_revenue")),
        "spent_fmt": format_amount_short((budget or {}).get("total_expenditure")),
        "surplus_fmt": format_amount_short((budget or {}).get("surplus_deficit")),
        "surplus_positive": ((budget or {}).get("surplus_deficit") or 0) >= 0,
        "property_tax_pct": (budget or {}).get("property_tax_pct_of_revenue"),
    })
