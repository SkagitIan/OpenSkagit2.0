from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import render
from django.views.decorators.http import require_POST

from core.views import CITY_PAGES
from .models import TaxShiftSignup

from .queries import (
    search_parcels,
    get_parcel,
    get_tax_summary,
    get_levy_code_median,
    get_levy_code_effective_rate_median,
    get_county_median,
    get_county_effective_rate_median,
    get_county_taxable_effective_rate_median,
    get_agency_crosswalk,
    get_county_total_for_mcag,
    get_parcel_history,
    get_tax_shock,
)
from .utils import (
    group_levy_rows,
    format_currency,
    format_amount_short,
    format_delta_currency,
    format_delta_pct,
    compute_yoy_breakdown,
    get_agency_color,
    get_agency_info,
    build_comparison_context,
    build_agency_donut,
    build_display_history,
    build_history_story,
    build_latest_change,
    build_money_buckets,
    build_exemption_context,
    reconcile_group_totals,
)


def tax_home(request):
    return render(request, "taxtool/base.html", {"city_pages": CITY_PAGES})


def tax_search(request):
    q = request.GET.get("q", "").strip()
    parcels = search_parcels(q) if len(q) >= 2 else []
    return render(request, "taxtool/_suggestions.html", {"parcels": parcels, "q": q})


@require_POST
def tax_signup(request):
    email = request.POST.get("email", "").strip().lower()
    address_or_parcel = request.POST.get("address_or_parcel", "").strip()

    try:
        validate_email(email)
    except ValidationError:
        return render(request, "taxtool/_signup_result.html", {
            "success": False,
            "message": "Enter a valid email address.",
        }, status=400)

    TaxShiftSignup.objects.update_or_create(
        email=email,
        defaults={
            "address_or_parcel": address_or_parcel[:255],
            "source": "taxshift_home",
        },
    )
    return render(request, "taxtool/_signup_result.html", {
        "success": True,
        "message": "You're on the list. We'll send tax shift updates as this rolls out.",
    })


def tax_parcel(request, parcel_number):
    template_name = "taxtool/_bill.html" if request.headers.get("HX-Request") else "taxtool/parcel_page.html"
    parcel = get_parcel(parcel_number)
    if not parcel:
        return render(request, template_name, {
            "error": "Parcel not found.",
            "parcel_number": parcel_number,
            "city_pages": CITY_PAGES,
        })

    history = build_display_history(parcel, get_parcel_history(parcel_number))
    current_tax_amount = history[0]["tax_amount"] if history else parcel.get("total_taxes")
    summary_rows = get_tax_summary(parcel_number, parcel.get("tax_year"))
    grouped = group_levy_rows(summary_rows)
    reconciliation = reconcile_group_totals(grouped, current_tax_amount)
    grouped = reconciliation["groups"]

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
    levy_rate_median = get_levy_code_effective_rate_median(parcel.get("levy_code"))
    county_rate_median = get_county_effective_rate_median()
    county_taxable_rate_median = get_county_taxable_effective_rate_median()
    latest_change = build_latest_change(history)
    money_story = build_money_buckets(grouped)
    agency_donut = build_agency_donut(grouped)
    history_story = build_history_story(history)
    current_assessed_value = history[0]["total_value"] if history else parcel.get("assessed_value")
    exemption_context = build_exemption_context(parcel, current_tax_amount)
    current_taxable_value = parcel.get("tax_statement_taxable_value") or parcel.get("taxable_value")
    comparison = build_comparison_context(
        current_tax_amount,
        current_assessed_value,
        current_taxable_value,
        exemption_context,
        county_rate_median,
        levy_rate_median,
        county_taxable_rate_median,
    )
    payable_year = int(parcel["tax_year"]) + 1 if parcel.get("tax_year") else None
    tax_shock = get_tax_shock(parcel_number)
    tax_shock_ctx = None
    if tax_shock:
        main_driver = tax_shock["main_driver"]
        direction_word = "increase" if tax_shock["delta_positive"] else "decrease"
        if main_driver == "voter":
            driver_label = "Voter-approved levies"
            reason = f"{tax_shock['main_driver_pct']}% of the {direction_word} came from voter-approved levy changes, not property value."
        elif main_driver == "value":
            driver_label = "Property value"
            reason = f"{tax_shock['main_driver_pct']}% of the {direction_word} came from assessed value changes."
        else:
            driver_label = "Regular levy rates"
            reason = f"{tax_shock['main_driver_pct']}% of the {direction_word} came from regular levy/rate changes."

        top_line = tax_shock["top_lines"][0] if tax_shock["top_lines"] else None
        delta_abs = abs(float(tax_shock["delta_tax"]))

        def effect_pct(value):
            if not delta_abs:
                return 0
            n = float(value)
            if tax_shock["delta_positive"] and n <= 0:
                return 0
            if not tax_shock["delta_positive"] and n >= 0:
                return 0
            return max(0, min(100, round(abs(n) / delta_abs * 100)))

        value_pct = effect_pct(tax_shock["value_effect"])
        voter_pct = effect_pct(tax_shock["voter_rate_effect"])
        other_pct = effect_pct(tax_shock["other_rate_effect"])
        total_pct = value_pct + voter_pct + other_pct
        if total_pct > 100:
            scale = 100 / total_pct
            value_pct = round(value_pct * scale)
            voter_pct = round(voter_pct * scale)
            other_pct = max(0, 100 - value_pct - voter_pct)
        displayed_main_pct = {
            "voter": voter_pct,
            "value": value_pct,
            "other": other_pct,
        }.get(main_driver, tax_shock["main_driver_pct"])

        if main_driver == "voter":
            reason = f"{displayed_main_pct}% of the explained change came from voter-approved levy changes, not property value."
        elif main_driver == "value":
            reason = f"{displayed_main_pct}% of the explained change came from assessed value changes."
        else:
            reason = f"{displayed_main_pct}% of the explained change came from regular levy/rate changes."

        tax_shock_ctx = {
            "year_new": tax_shock["year_new"],
            "year_old": tax_shock["year_old"],
            "direction_word": direction_word,
            "delta_fmt": format_delta_currency(tax_shock["delta_tax"]),
            "delta_positive": tax_shock["delta_positive"],
            "driver_label": driver_label,
            "reason": reason,
            "main_driver_pct": displayed_main_pct,
            "value_pct": value_pct,
            "voter_pct": voter_pct,
            "other_pct": other_pct,
            "value_effect_fmt": format_delta_currency(tax_shock["value_effect"]),
            "voter_effect_fmt": format_delta_currency(tax_shock["voter_rate_effect"]),
            "other_effect_fmt": format_delta_currency(tax_shock["other_rate_effect"]),
            "top_line_name": (top_line.get("district_name") or top_line["levy_name"]).title() if top_line else None,
            "top_line_effect_fmt": format_delta_currency(top_line["rate_effect"]) if top_line else None,
        }

    return render(request, template_name, {
        "parcel": parcel,
        "grouped": grouped,
        "total_fmt": format_currency(current_tax_amount),
        "payable_year": payable_year,
        "levy_code_median_fmt": format_currency(levy_code_median) if levy_code_median else None,
        "county_median_fmt": format_currency(county_median) if county_median else None,
        "tax_shock": tax_shock_ctx,
        "latest_change": latest_change,
        "money_story": money_story,
        "agency_donut": agency_donut,
        "history_story": history_story,
        "comparison": comparison,
        "exemption_context": exemption_context,
        "data_sources": {
            "bill_year": parcel.get("tax_year"),
            "payable_year": payable_year,
            "current_bill_fmt": format_currency(current_tax_amount),
            "history_source": "Current assessor roll merged with parcel tax statement history",
            "agency_source_total_fmt": format_currency(reconciliation["source_total"]),
            "agency_adjusted": reconciliation["adjusted"],
            "agency_difference_fmt": format_delta_currency(reconciliation["difference"]),
            "skagit_property_search_url": "https://www.skagitcounty.net/search/property/",
            "sao_fit_url": "https://sao.wa.gov/taxonomy/term/31",
            "dor_skagit_url": "https://dor.wa.gov/taxes-rates/property-tax/county-reports/skagit-county",
            "dor_levy_limit_url": "https://dor.wa.gov/forms-publications/publications-subject/tax-topics/property-tax-how-1-property-tax-levy-limit-works",
            "dor_senior_exemption_url": "https://dor.wa.gov/taxes-rates/property-tax/property-tax-exemption-seniors-people-retired-due-disability-and-veterans-disabilities",
            "dor_exemptions_url": "https://dor.wa.gov/taxes-rates/property-tax/property-tax-exemptions-and-deferrals",
        },
        "city_pages": CITY_PAGES,
    })


def tax_yoy(request, parcel_number):
    parcel = get_parcel(parcel_number)
    if not parcel:
        return render(request, "taxtool/_yoy.html", {"error": "Parcel not found.", "parcel_number": parcel_number})

    history = build_display_history(parcel, get_parcel_history(parcel_number))
    if not history:
        return render(request, "taxtool/_yoy.html", {"parcel": parcel, "no_history": True})

    breakdowns = compute_yoy_breakdown(history)

    latest_ctx = None
    if breakdowns:
        b = breakdowns[0]
        rate_delta = b["rate_b"] - b["rate_a"]
        rate_delta_sign = "+" if rate_delta >= 0 else "-"
        latest_ctx = {
            "year_b": b["year_b"],
            "year_a": b["year_a"],
            "tax_b_fmt": format_currency(b["tax_b"]),
            "tax_a_fmt": format_currency(b["tax_a"]),
            "delta_fmt": format_delta_currency(b["delta_tax"]),
            "delta_pct_fmt": format_delta_pct(b["delta_pct"]),
            "delta_positive": b["delta_tax"] >= 0,
            "val_b_fmt": format_currency(b["val_b"]),
            "val_a_fmt": format_currency(b["val_a"]),
            "delta_val_fmt": format_delta_currency(b["delta_val"]),
            "delta_val_pct_fmt": format_delta_pct(b["delta_val_pct"]),
            "rate_a_fmt": f"{b['rate_a']:.2f}",
            "rate_b_fmt": f"{b['rate_b']:.2f}",
            "rate_delta_fmt": f"{rate_delta_sign}{abs(rate_delta):.2f} per $1,000",
            "value_effect_fmt": format_delta_currency(b["value_effect"]),
            "value_effect_positive": b["value_effect"] >= 0,
            "rate_effect_fmt": format_delta_currency(b["rate_effect"]),
            "rate_effect_positive": b["rate_effect"] >= 0,
        }

    history_rows = []
    for i, row in enumerate(history):
        bd = breakdowns[i] if i < len(breakdowns) else None
        history_rows.append({
            "tax_year": row["tax_year"],
            "total_value_fmt": format_currency(row["total_value"]),
            "tax_amount_fmt": format_currency(row["tax_amount"]),
            "delta_fmt": format_delta_currency(bd["delta_tax"]) if bd else "",
            "delta_pct_fmt": format_delta_pct(bd["delta_pct"]) if bd else "",
            "delta_positive": bd["delta_tax"] >= 0 if bd else None,
        })

    return render(request, "taxtool/_yoy.html", {
        "parcel": parcel,
        "latest": latest_ctx,
        "history_rows": history_rows,
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
