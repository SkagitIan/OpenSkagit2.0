from .queries import (
    get_parcel,
    get_tax_summary,
    get_levy_code_median,
    get_levy_code_effective_rate_median,
    get_county_median,
    get_county_effective_rate_median,
    get_county_taxable_effective_rate_median,
    get_tax_shock,
    get_tax_shock_history,
    get_parcel_history,
)
from .utils import (
    group_levy_rows,
    format_currency,
    format_delta_currency,
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


def attach_reason_history_drivers(history_story, shock_history):
    if not history_story or not history_story.get("reason_history"):
        return history_story
    for reason in history_story["reason_history"]:
        shock = shock_history.get((reason["year_old"], reason["year_new"]))
        if not shock:
            continue
        driver_lines = []
        for line in shock.get("top_lines", [])[:3]:
            rate_delta = line.get("rate_delta") or 0
            driver_lines.append({
                "name": (line.get("district_name") or line.get("agency_name") or line.get("levy_name") or "Taxing district").title(),
                "rate_delta_fmt": f"{'+' if rate_delta >= 0 else '-'}{abs(float(rate_delta)):.2f} per $1,000",
                "effect_fmt": format_delta_currency(line.get("rate_effect")),
            })
        reason["drivers"] = driver_lines
        reason["driver_note"] = "Estimated using the parcel's current levy code and historical levy-rate files."
    return history_story


def build_tax_report_context(parcel_number, city_pages=None):
    parcel = get_parcel(parcel_number)
    if not parcel:
        return {
            "error": "Parcel not found.",
            "parcel_number": parcel_number,
            "city_pages": city_pages or [],
        }

    history = build_display_history(parcel, get_parcel_history(parcel_number))
    current_tax_amount = history[0]["tax_amount"] if history else parcel.get("total_taxes")
    summary_rows = get_tax_summary(parcel_number, parcel.get("tax_year"))
    grouped = group_levy_rows(summary_rows)
    reconciliation = reconcile_group_totals(grouped, current_tax_amount)
    grouped = reconciliation["groups"]

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
    history_story = attach_reason_history_drivers(history_story, get_tax_shock_history(parcel_number, limit=7))
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
    tax_shock_ctx = _build_tax_shock_context(get_tax_shock(parcel_number))

    return {
        "parcel": parcel,
        "grouped": grouped,
        "total_fmt": format_currency(current_tax_amount),
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
            "current_bill_fmt": format_currency(current_tax_amount),
            "history_source": "Current assessor roll merged with parcel tax statement history",
            "agency_allocation_note": "Agency amounts are reconstructed from levy rates and assessed value, then reconciled to the displayed parcel bill when the sources do not match exactly.",
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
        "city_pages": city_pages or [],
        "report_data": {
            "current_tax_amount": current_tax_amount,
            "current_assessed_value": current_assessed_value,
            "current_taxable_value": current_taxable_value,
            "summary_row_count": len(summary_rows),
            "history": history,
            "yoy_breakdowns": compute_yoy_breakdown(history),
            "reconciliation": reconciliation,
            "levy_rate_median": levy_rate_median,
            "county_rate_median": county_rate_median,
            "county_taxable_rate_median": county_taxable_rate_median,
        },
    }


def _build_tax_shock_context(tax_shock):
    if not tax_shock:
        return None

    main_driver = tax_shock["main_driver"]
    direction_word = "increase" if tax_shock["delta_positive"] else "decrease"
    if main_driver == "voter":
        driver_label = "Voter-approved levies"
    elif main_driver == "value":
        driver_label = "Property value"
    else:
        driver_label = "Regular levy rates"

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

    return {
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
