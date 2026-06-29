from decimal import Decimal

TYPE_COLORS = {
    "state":    "#94a3b8",
    "school":   "#3b82f6",
    "county":   "#8b5cf6",
    "city":     "#10b981",
    "fire":     "#ef4444",
    "hospital": "#f97316",
    "library":  "#eab308",
    "port":     "#06b6d4",
    "ems":      "#ec4899",
    "cemetery": "#6b7280",
    "other":    "#d1d5db",
}


def group_levy_rows(rows):
    """
    Collapse v_parcel_tax_summary rows into display segments:
    - state_levy rows → single "Washington State" segment
    - needs_review rows → single "Other Local Districts" segment
    - reports_independently / sub_levy → grouped by MCAG
    """
    groups = {}
    for row in rows:
        status = row.get("reporting_status", "")
        if status == "state_levy":
            key = "__STATE__"
            label = "WA State School Levy"
            mcag = None
        elif status == "needs_review":
            key = "__OTHER__"
            label = "Other Local Districts"
            mcag = row.get("mcag")
        else:
            mcag = row.get("mcag") or "__OTHER__"
            key = mcag
            label = row.get("agency_name") or "Unknown Agency"

        if key not in groups:
            groups[key] = {
                "key": key,
                "mcag": mcag if key not in ("__STATE__", "__OTHER__") else None,
                "label": label,
                "total": Decimal("0"),
                "sao_fit_url": row.get("sao_fit_url"),
            }
        groups[key]["total"] += Decimal(str(row.get("total_tax") or 0))

    total_bill = sum(g["total"] for g in groups.values())
    for g in groups.values():
        g["pct"] = round(100 * float(g["total"]) / float(total_bill), 1) if total_bill else 0

    return sorted(groups.values(), key=lambda x: x["total"], reverse=True)


def format_currency(amount):
    """Format as $3,610 — no cents, with comma separator."""
    if amount is None:
        return "$0"
    try:
        return f"${int(round(float(amount))):,}"
    except (TypeError, ValueError):
        return "$0"


def format_amount_short(amount):
    """Format large numbers as $9.2M or $180K."""
    if amount is None:
        return "N/A"
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return "N/A"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${int(n):,}"


def format_delta_currency(amount):
    """Format as +$3,285 or -$1,234 with explicit sign."""
    if amount is None:
        return "—"
    try:
        n = float(amount)
        if int(round(n)) == 0:
            return "$0"
        if n >= 0:
            return f"+${int(round(n)):,}"
        return f"-${int(round(abs(n))):,}"
    except (TypeError, ValueError):
        return "—"


def format_delta_pct(pct):
    """Format as +8.5% or -3.2% with explicit sign."""
    if pct is None:
        return ""
    try:
        n = float(pct)
        if n >= 0:
            return f"+{n:.1f}%"
        return f"-{abs(n):.1f}%"
    except (TypeError, ValueError):
        return ""


def compute_yoy_breakdown(history_rows):
    """
    Given history rows (desc order by tax_year), return list of YoY dicts, most recent first.
    Uses symmetric (Divisia) decomposition: value_effect + rate_effect ≈ delta_tax.
    """
    results = []
    rows = list(history_rows)
    for i in range(len(rows) - 1):
        b = rows[i]       # newer year
        a = rows[i + 1]   # older year
        try:
            tax_b = float(b["tax_amount"])
            tax_a = float(a["tax_amount"])
            val_b = float(b["total_value"])
            val_a = float(a["total_value"])
        except (TypeError, ValueError):
            continue
        if tax_a <= 0 or val_a <= 0 or val_b <= 0:
            continue
        delta_tax = tax_b - tax_a
        rate_a = tax_a / val_a * 1000   # effective $/1,000 of assessed value
        rate_b = tax_b / val_b * 1000
        value_effect = (val_b - val_a) * (rate_a + rate_b) / 2 / 1000
        rate_effect = (rate_b - rate_a) * (val_a + val_b) / 2 / 1000
        results.append({
            "year_b": b["tax_year"],
            "year_a": a["tax_year"],
            "tax_b": tax_b,
            "tax_a": tax_a,
            "delta_tax": delta_tax,
            "delta_pct": delta_tax / tax_a * 100,
            "val_b": val_b,
            "val_a": val_a,
            "delta_val": val_b - val_a,
            "delta_val_pct": (val_b - val_a) / val_a * 100,
            "rate_a": rate_a,
            "rate_b": rate_b,
            "value_effect": value_effect,
            "rate_effect": rate_effect,
        })
    return results


def _as_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


EXEMPTION_LABELS = {
    "SNR/DSBL": "Senior/disabled exemption",
    "EX.ST": "State exemption",
    "EX.CITY": "City exemption",
    "EX.CTY": "County exemption",
    "EX.BIA": "Federal/tribal exemption",
    "EX.FED": "Federal exemption",
    "EX.DOR": "Department of Revenue exemption",
    "EX.PORT": "Port district exemption",
    "EX.TCO": "Taxing district exemption",
    "EX.SCH": "School district exemption",
    "EX.DIKE": "Dike district exemption",
    "EX.PUD": "Public utility district exemption",
    "EX.NONP": "Nonprofit exemption",
    "EX.HOS": "Hospital district exemption",
    "EX.FIRE": "Fire district exemption",
    "EX.ROW": "Right-of-way exemption",
    "EX.HSING AUTH": "Housing authority exemption",
    "EX.CEM": "Cemetery exemption",
    "U500": "Utility exemption",
    "DOR": "Department of Revenue exemption",
}


def _split_exemption_codes(raw_codes):
    if raw_codes is None:
        return []
    raw = str(raw_codes).strip()
    if not raw:
        return []
    for separator in (";", "|", "\n", "\r"):
        raw = raw.replace(separator, ",")
    return [code.strip() for code in raw.split(",") if code.strip()]


def _exemption_label(code):
    normalized = str(code or "").strip().upper()
    return EXEMPTION_LABELS.get(normalized, f"Exemption code {code}")


def build_exemption_context(parcel, total_taxes=None):
    """Return copy-safe exemption/value fields for the tax report."""
    raw_codes = _split_exemption_codes(parcel.get("exemptions"))
    normalized_codes = [code.upper() for code in raw_codes]
    assessed_value = _as_float(parcel.get("assessed_value"))
    taxable_value = _as_float(
        parcel.get("tax_statement_taxable_value")
        or parcel.get("taxable_value")
        or parcel.get("assessed_value")
    )
    senior_adjustment = _as_float(parcel.get("senior_exemption_adjustment"))
    taxable_gap = max(0, assessed_value - taxable_value)
    has_exemption = bool(raw_codes) or senior_adjustment > 0 or taxable_gap > 0
    is_senior = "SNR/DSBL" in normalized_codes or senior_adjustment > 0
    if not has_exemption:
        return {
            "has_exemption": False,
            "is_senior": False,
            "uses_taxable_value": False,
            "raw_codes": [],
            "labels": [],
            "comparison_intro": "Compared by effective tax rate, not total bill size. Levy-area rates are usually the same for nearby parcels, so this compares your rate with the countywide median.",
            "comparison_note": "Effective rate means tax bill divided by assessed value, shown as dollars per $1,000. It makes unlike home values easier to compare.",
        }

    labels = [_exemption_label(code) for code in raw_codes]
    if is_senior and "Senior/disabled exemption" not in labels:
        labels.insert(0, "Senior/disabled exemption")

    exempted_value = senior_adjustment if is_senior and senior_adjustment > 0 else taxable_gap
    relief = None
    total = _as_float(total_taxes)
    if total > 0 and taxable_value > 0 and exempted_value > 0:
        relief = exempted_value * (total / taxable_value)

    code_summary = ", ".join(labels) if labels else "Exemption"
    first_code = raw_codes[0] if raw_codes else None
    if is_senior:
        card_title = "Exemption affects taxable value"
        card_body = (
            f"This parcel appears to receive a senior/disabled exemption. Its assessed value is "
            f"{format_currency(assessed_value)}, but taxes are applied to a lower taxable value of "
            f"{format_currency(taxable_value)} after a {format_currency(exempted_value)} adjustment."
        )
    elif taxable_gap > 0:
        card_title = "Exemption affects taxable value"
        card_body = (
            f"This parcel has {code_summary}. Its assessed value is {format_currency(assessed_value)}, "
            f"but taxes appear to be applied to a lower taxable value of {format_currency(taxable_value)}."
        )
    else:
        card_title = "Exemption noted"
        if first_code and code_summary != f"Exemption code {first_code}":
            exemption_phrase = f"{code_summary} (code {first_code})"
        else:
            exemption_phrase = code_summary
        card_body = (
            f"This parcel has {exemption_phrase}. Its tax bill may be based on taxable value rather "
            "than full assessed value."
        )

    return {
        "has_exemption": True,
        "is_senior": is_senior,
        "uses_taxable_value": taxable_value > 0,
        "has_taxable_gap": taxable_gap > 0,
        "raw_codes": raw_codes,
        "labels": labels,
        "code_summary": code_summary,
        "card_title": card_title,
        "card_body": card_body,
        "assessed_value_fmt": format_currency(assessed_value),
        "taxable_value_fmt": format_currency(taxable_value),
        "exempted_value_fmt": format_currency(exempted_value),
        "estimated_tax_relief_fmt": format_currency(relief) if relief and relief > 0 else None,
        "comparison_intro": "Compared by tax per $1,000 of taxable value after exemptions.",
        "comparison_note": "For parcels with exemptions, this rate uses the taxable value the bill is based on, not the full assessed value.",
        "history_note": "Historical assessed values do not always show exemption adjustments; current taxable value is shown separately.",
        "money_note": "Agency amounts are based on the actual bill after exemptions.",
    }


def build_display_history(parcel, history_rows):
    """Merge the current parcel roll into history when it is newer than scraped history."""
    rows = [dict(row) for row in history_rows]
    current_year = parcel.get("tax_year")
    if not current_year:
        return rows

    try:
        current_year_int = int(current_year)
    except (TypeError, ValueError):
        return rows

    current_tax = parcel.get("total_taxes")
    current_value = parcel.get("assessed_value") or parcel.get("taxable_value")
    if current_tax is None or current_value is None:
        return rows

    current_row = {
        "tax_year": current_year_int,
        "total_value": current_value,
        "tax_amount": current_tax,
        "building_value": None,
        "land_value": None,
    }

    replaced = False
    for index, row in enumerate(rows):
        try:
            row_year = int(row.get("tax_year"))
        except (TypeError, ValueError):
            continue
        if row_year == current_year_int:
            rows[index] = current_row
            replaced = True
            break

    if not replaced:
        rows.append(current_row)

    return sorted(rows, key=lambda row: int(row["tax_year"]), reverse=True)


def reconcile_group_totals(grouped, target_total):
    """Scale levy detail groups to the authoritative bill total when sources differ."""
    target = Decimal(str(target_total or 0))
    source_total = sum(Decimal(str(group.get("total") or 0)) for group in grouped)
    if target <= 0 or source_total <= 0:
        return {
            "groups": grouped,
            "source_total": source_total,
            "target_total": target,
            "adjusted": False,
            "difference": target - source_total,
        }

    difference = target - source_total
    should_adjust = abs(difference) > Decimal("0.01")
    if not should_adjust:
        return {
            "groups": grouped,
            "source_total": source_total,
            "target_total": target,
            "adjusted": False,
            "difference": difference,
        }

    ratio = target / source_total
    adjusted_groups = []
    running_total = Decimal("0")
    for index, group in enumerate(grouped):
        adjusted = dict(group)
        if index == len(grouped) - 1:
            adjusted_total = target - running_total
        else:
            adjusted_total = (Decimal(str(group.get("total") or 0)) * ratio).quantize(Decimal("0.01"))
            running_total += adjusted_total
        adjusted["source_total"] = Decimal(str(group.get("total") or 0))
        adjusted["total"] = adjusted_total
        adjusted_groups.append(adjusted)

    for group in adjusted_groups:
        group["pct"] = round(100 * float(group["total"]) / float(target), 1) if target else 0

    return {
        "groups": adjusted_groups,
        "source_total": source_total,
        "target_total": target,
        "adjusted": True,
        "difference": difference,
    }


def _classify_money_bucket(group):
    label = str(group.get("label") or "").lower()
    mcag = str(group.get("mcag") or "")
    info = get_agency_info(group.get("mcag"))
    agency_type = str((info or {}).get("type") or "").lower()

    if group.get("key") == "__STATE__" or "school" in label or agency_type == "school":
        return "schools"
    if agency_type == "city" or "city" in label or mcag in {"0610", "0620", "0630", "0640"}:
        return "city"
    if agency_type == "county" or "county" in label:
        return "county"
    if agency_type in {"fire", "hospital", "port", "ems"}:
        return "care"
    if any(token in label for token in ("fire", "hospital", "health", "emergency", "ems", "port")):
        return "care"
    return "other"


def build_money_buckets(grouped):
    """Collapse agency groups into public-facing destination buckets."""
    bucket_defs = {
        "schools": {"label": "Schools", "color": "#1769e8", "total": Decimal("0")},
        "city": {"label": "City services", "color": "#13a874", "total": Decimal("0")},
        "county": {"label": "County government", "color": "#6f56d9", "total": Decimal("0")},
        "care": {"label": "Emergency / health / port", "color": "#e84d8a", "total": Decimal("0")},
        "other": {"label": "Other local districts", "color": "#94a3b8", "total": Decimal("0")},
    }

    for group in grouped:
        bucket_defs[_classify_money_bucket(group)]["total"] += Decimal(str(group.get("total") or 0))

    total = sum(bucket["total"] for bucket in bucket_defs.values())
    buckets = []
    gradient_parts = []
    cursor = 0.0
    for bucket in bucket_defs.values():
        if bucket["total"] <= 0:
            continue
        pct = round(100 * float(bucket["total"]) / float(total), 1) if total else 0
        next_cursor = cursor + pct
        gradient_parts.append(f"{bucket['color']} {cursor:.1f}% {next_cursor:.1f}%")
        buckets.append({
            **bucket,
            "total_fmt": format_currency(bucket["total"]),
            "pct": pct,
            "pct_fmt": f"{pct:.1f}%",
        })
        cursor = next_cursor

    return {
        "buckets": buckets,
        "gradient": ", ".join(gradient_parts) if gradient_parts else "#d8e1e8 0% 100%",
    }


def build_agency_donut(grouped):
    """Prepare every agency group for the full destination donut."""
    total = sum(Decimal(str(group.get("total") or 0)) for group in grouped)
    gradient_parts = []
    cursor = 0.0
    for group in grouped:
        pct = round(100 * float(group.get("total") or 0) / float(total), 1) if total else 0
        next_cursor = cursor + pct
        color = group.get("color") or "#94a3b8"
        gradient_parts.append(f"{color} {cursor:.1f}% {next_cursor:.1f}%")
        group["donut_pct"] = pct
        group["donut_pct_fmt"] = f"{pct:.1f}%"
        cursor = next_cursor

    return {
        "groups": grouped,
        "gradient": ", ".join(gradient_parts) if gradient_parts else "#d8e1e8 0% 100%",
    }


def build_latest_change(history_rows):
    """Return current/prior year narrative values from parcel history."""
    breakdowns = compute_yoy_breakdown(history_rows)
    if not breakdowns:
        return None

    b = breakdowns[0]
    rate_delta = b["rate_b"] - b["rate_a"]
    return {
        "year_new": b["year_b"],
        "year_old": b["year_a"],
        "tax_new_fmt": format_currency(b["tax_b"]),
        "tax_old_fmt": format_currency(b["tax_a"]),
        "delta_abs_fmt": format_currency(abs(b["delta_tax"])),
        "delta_fmt": format_delta_currency(b["delta_tax"]),
        "delta_pct_fmt": format_delta_pct(b["delta_pct"]),
        "delta_positive": b["delta_tax"] >= 0,
        "delta_zero": round(b["delta_tax"]) == 0,
        "direction": "up" if b["delta_tax"] >= 0 else "down",
        "value_new_fmt": format_currency(b["val_b"]),
        "value_old_fmt": format_currency(b["val_a"]),
        "value_delta_fmt": format_delta_currency(b["delta_val"]),
        "value_delta_pct_fmt": format_delta_pct(b["delta_val_pct"]),
        "value_delta_positive": b["delta_val"] >= 0,
        "value_direction": "up" if b["delta_val"] >= 0 else "down",
        "rate_old_fmt": f"{b['rate_a']:.2f}",
        "rate_new_fmt": f"{b['rate_b']:.2f}",
        "rate_delta_fmt": f"{'+' if rate_delta >= 0 else '-'}{abs(rate_delta):.2f} per $1,000",
        "value_effect_fmt": format_delta_currency(b["value_effect"]),
        "value_effect_positive": b["value_effect"] >= 0,
        "rate_effect_fmt": format_delta_currency(b["rate_effect"]),
        "rate_effect_positive": b["rate_effect"] >= 0,
    }


def build_history_story(history_rows):
    """Prepare chronological chart/table values for the tax story section."""
    rows = sorted(history_rows, key=lambda row: int(row["tax_year"]))
    if not rows:
        return None

    tax_values = [_as_float(row.get("tax_amount")) for row in rows]
    value_values = [_as_float(row.get("total_value")) for row in rows]
    max_tax = max(tax_values) if tax_values else 0
    min_tax = min(tax_values) if tax_values else 0
    max_value = max(value_values) if value_values else 0
    min_value = min(value_values) if value_values else 0
    tax_padding = max((max_tax - min_tax) * 0.12, 100)
    value_padding = max((max_value - min_value) * 0.12, 10_000)
    tax_min_axis = max(0, min_tax - tax_padding)
    tax_max_axis = max_tax + tax_padding
    value_min_axis = max(0, min_value - value_padding)
    value_max_axis = max_value + value_padding
    tax_span = max(tax_max_axis - tax_min_axis, 1)
    value_span = max(value_max_axis - value_min_axis, 1)
    width = 760
    height = 300
    left = 74
    right = 78
    top = 34
    bottom = 52
    plot_w = width - left - right
    plot_h = height - top - bottom

    tax_points = []
    value_points = []
    for index, row in enumerate(rows):
        denominator = max(len(rows) - 1, 1)
        x = left + (index / denominator) * plot_w
        tax_y = top + (tax_max_axis - _as_float(row.get("tax_amount"))) / tax_span * plot_h
        value_y = top + (value_max_axis - _as_float(row.get("total_value"))) / value_span * plot_h
        tax_points.append({
            "x": round(x, 1),
            "y": round(tax_y, 1),
            "year": row["tax_year"],
            "tax_fmt": format_currency(row["tax_amount"]),
            "value_fmt": format_currency(row["total_value"]),
        })
        value_points.append({
            "x": round(x, 1),
            "y": round(value_y, 1),
            "year": row["tax_year"],
            "value_fmt": format_currency(row["total_value"]),
            "tax_fmt": format_currency(row["tax_amount"]),
        })

    axis_rows = []
    for index in range(4):
        ratio = index / 3
        y = round(top + ratio * plot_h, 1)
        value_tick = value_max_axis - ratio * value_span
        tax_tick = tax_max_axis - ratio * tax_span
        axis_rows.append({
            "y": y,
            "value_label": f"${round(value_tick / 1000):,.0f}k",
            "tax_label": format_currency(tax_tick),
        })

    first = rows[0]
    latest = rows[-1]
    growth = None
    if _as_float(first.get("tax_amount")) > 0 and len(rows) > 1:
        growth = (_as_float(latest.get("tax_amount")) / _as_float(first.get("tax_amount")) - 1) * 100

    return {
        "points": tax_points,
        "tax_points": tax_points,
        "value_points": value_points,
        "axis_rows": axis_rows,
        "plot_left": left,
        "plot_right": width - right,
        "plot_top": top,
        "plot_bottom": height - bottom,
        "tax_polyline": " ".join(f"{point['x']},{point['y']}" for point in tax_points),
        "value_polyline": " ".join(f"{point['x']},{point['y']}" for point in value_points),
        "selected_rows": [{
            "tax_year": row["tax_year"],
            "tax_amount_fmt": format_currency(row["tax_amount"]),
            "total_value_fmt": format_currency(row["total_value"]),
        } for row in rows],
        "first_year": first["tax_year"],
        "first_tax_fmt": format_currency(first["tax_amount"]),
        "latest_year": latest["tax_year"],
        "latest_tax_fmt": format_currency(latest["tax_amount"]),
        "growth_text": (
            f"up {growth:.0f}% since {first['tax_year']}"
            if growth is not None and growth >= 0
            else f"down {abs(growth):.0f}% since {first['tax_year']}"
            if growth is not None
            else "available history"
        ),
    }


def format_rate(amount):
    if amount is None:
        return "N/A"
    try:
        return f"${float(amount):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def format_delta_rate(amount):
    if amount is None:
        return ""
    try:
        n = float(amount)
        if abs(n) < 0.005:
            return "$0.00"
        if n > 0:
            return f"+${n:.2f}"
        return f"-${abs(n):.2f}"
    except (TypeError, ValueError):
        return ""


def build_comparison_context(
    total_taxes,
    assessed_value,
    taxable_value,
    exemption_context,
    county_rate_median,
    levy_rate_median,
    county_taxable_rate_median=None,
):
    total = _as_float(total_taxes)
    use_taxable = bool((exemption_context or {}).get("has_exemption")) and _as_float(taxable_value) > 0
    value = _as_float(taxable_value if use_taxable else assessed_value)
    your_rate = total / value * 1000 if value > 0 else None
    county_median = county_taxable_rate_median if use_taxable and county_taxable_rate_median is not None else county_rate_median
    basis_label = "taxable value" if use_taxable else "assessed value"
    raw_items = [
        ("county", "Skagit County median", county_median),
        ("levy", "Your levy area median", levy_rate_median),
        ("your", "Your property", your_rate),
    ]
    available_rates = [float(rate) for _, _, rate in raw_items if rate is not None]
    if not available_rates:
        return {"your": None, "county": None, "levy": None, "items": [], "basis_label": basis_label}

    min_rate = min(available_rates)
    max_rate = max(available_rates)
    midpoint = (min_rate + max_rate) / 2
    half_span = max((max_rate - min_rate) / 2, 0.25)
    min_rate = midpoint - half_span
    max_rate = midpoint + half_span
    span = max_rate - min_rate

    def position(rate):
        return round(8 + (float(rate) - min_rate) / span * 84, 1)

    items = []
    for key, label, rate in raw_items:
        if rate is None:
            item = None
        else:
            delta = float(your_rate or 0) - float(rate)
            item = {
                "key": key,
                "label": label,
                "rate": float(rate),
                "rate_fmt": f"{format_rate(rate)} per $1,000",
                "short_rate_fmt": format_rate(rate),
                "delta_fmt": format_delta_rate(delta),
                "paid_more": delta >= 0,
                "position": position(rate),
                "is_your": key == "your",
            }
        items.append(item)

    by_key = {item["key"]: item for item in items if item}
    county_delta = abs(float(your_rate or 0) - float(county_median)) if county_median is not None and your_rate is not None else None
    meaningful_delta = county_delta if county_delta is not None else 0
    if meaningful_delta < 0.10:
        verdict = "Your effective tax rate is about typical."
        verdict_detail = f"The differences are only a few cents per $1,000 of {basis_label}."
        verdict_tone = "typical"
    elif by_key.get("county") and by_key["county"]["paid_more"]:
        verdict = "Your effective tax rate is above the county median."
        verdict_detail = f"That means you pay more per $1,000 of {basis_label} than the typical Skagit County parcel."
        verdict_tone = "high"
    else:
        verdict = "Your effective tax rate is below the county median."
        verdict_detail = f"That means you pay less per $1,000 of {basis_label} than the typical Skagit County parcel."
        verdict_tone = "low"

    return {
        "county": by_key.get("county"),
        "levy": by_key.get("levy"),
        "your": by_key.get("your"),
        "items": [item for item in items if item and item["key"] != "levy"],
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "verdict_tone": verdict_tone,
        "basis_label": basis_label,
        "uses_taxable_value": use_taxable,
    }


def get_agency_color(agency_type):
    """Return hex color for a given agency type string."""
    return TYPE_COLORS.get(str(agency_type).lower(), TYPE_COLORS["other"])


def get_agency_info(mcag):
    """Look up an agency by MCAG in the loaded JSON data."""
    from taxtool.apps import TaxtoolConfig
    return TaxtoolConfig.agencies.get(str(mcag)) if mcag else None
