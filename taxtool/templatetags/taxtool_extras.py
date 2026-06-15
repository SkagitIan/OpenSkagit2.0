from django import template

register = template.Library()


@register.filter
def currency(value):
    """Format a number as $3,610 — no cents."""
    if value is None:
        return "$0"
    try:
        return f"${int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "$0"


@register.filter
def pct_width(value):
    """Return a CSS width string clamped to 1–100%."""
    try:
        v = float(value)
        v = max(1.0, min(100.0, v))
        return f"{v}%"
    except (TypeError, ValueError):
        return "1%"
