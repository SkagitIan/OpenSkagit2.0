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
            label = "Washington State"
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


def get_agency_color(agency_type):
    """Return hex color for a given agency type string."""
    return TYPE_COLORS.get(str(agency_type).lower(), TYPE_COLORS["other"])


def get_agency_info(mcag):
    """Look up an agency by MCAG in the loaded JSON data."""
    from taxtool.apps import TaxtoolConfig
    return TaxtoolConfig.agencies.get(str(mcag)) if mcag else None
