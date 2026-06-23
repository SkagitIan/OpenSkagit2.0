import hmac

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from urllib.parse import urlencode

from .services import DEFAULT_TAB, SORT_FIELDS, TAB_LOOKUP, TABS, fetch_tab_rows, tab_counts


FILTER_KEYS = [
    "min_years",
    "min_due",
    "improved",
    "place",
    "min_land_ratio",
    "min_acres",
    "max_building",
    "min_land_value",
    "min_cluster",
]

PAGE_SIZE = 50


def dashboard(request):
    password = getattr(settings, "OPPORTUNITY_DASHBOARD_PASSWORD", "")
    password_error = ""
    if request.method == "POST":
        submitted = request.POST.get("password", "")
        if password and hmac.compare_digest(submitted, password):
            request.session["opportunity_dashboard_unlocked"] = True
        else:
            password_error = "That password did not work."

    if not request.session.get("opportunity_dashboard_unlocked"):
        return render(
            request,
            "opportunity/dashboard.html",
            {
                "locked": True,
                "password_configured": bool(password),
                "password_error": password_error,
            },
        )

    selected_tab = request.GET.get("tab", DEFAULT_TAB)
    if selected_tab not in TAB_LOOKUP:
        selected_tab = DEFAULT_TAB

    filters = {key: request.GET.get(key, "") for key in FILTER_KEYS}
    sort = request.GET.get("sort", "")
    if sort not in SORT_FIELDS:
        sort = ""
    direction = request.GET.get("dir", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"

    page = _positive_int(request.GET.get("page"), 1)
    fetch_limit = page * PAGE_SIZE
    all_rows = fetch_tab_rows(selected_tab, filters, limit=fetch_limit, sort=sort, direction=direction)
    rows = all_rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    has_previous = page > 1
    has_next = len(all_rows) == fetch_limit
    counts = tab_counts(filters)
    sort_links = {
        key: _sort_url(selected_tab, sort, direction, key)
        for key in ["assessed", "zone", "risk", "location"]
    }

    return render(
        request,
        "opportunity/dashboard.html",
        {
            "tabs": TABS,
            "selected_tab": selected_tab,
            "selected_tab_obj": TAB_LOOKUP[selected_tab],
            "counts": counts,
            "rows": rows,
            "filters": filters,
            "sort": sort,
            "direction": direction,
            "sort_links": sort_links,
            "page": page,
            "has_previous": has_previous,
            "has_next": has_next,
            "previous_url": _page_url(selected_tab, sort, direction, page - 1) if has_previous else "",
            "next_url": _page_url(selected_tab, sort, direction, page + 1) if has_next else "",
        },
    )


def _sort_url(tab: str, current_sort: str, current_direction: str, key: str) -> str:
    next_direction = "asc" if current_sort != key or current_direction == "desc" else "desc"
    return f"{reverse('opportunity_dashboard')}?{urlencode({'tab': tab, 'sort': key, 'dir': next_direction})}"


def _page_url(tab: str, sort: str, direction: str, page: int) -> str:
    params = {"tab": tab, "page": page}
    if sort:
        params["sort"] = sort
        params["dir"] = direction
    return f"{reverse('opportunity_dashboard')}?{urlencode(params)}"


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
