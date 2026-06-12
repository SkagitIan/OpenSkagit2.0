from django import template

register = template.Library()


@register.filter
def dict_value(d, key):
    """Return d[key] for use with a variable key in templates."""
    if isinstance(d, dict):
        return d.get(key, "")
    return ""
