from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from .ai_search import (
    FEEDBACK_REASONS,
    display_rows_for_search,
    ensure_ai_search_worker,
    recent_searches_for_user,
    record_search_feedback,
    saved_searches_for_user,
    start_ai_opportunity_search,
    start_refresh_opportunity_search,
)
from .models import OpportunitySavedParcel, OpportunitySearch
from .services import (
    DEFAULT_TAB,
    TAB_LOOKUP,
    TABS,
    dashboard_context,
    fetch_tab_rows,
    latest_assessor_sync_summary,
    mark_saved,
    parcel_detail,
    tab_counts,
    watchlist_rows,
)


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
DISCLAIMER = (
    "Parcel Book shows screening signals from public records. These are not entitlement approvals, "
    "zoning determinations, legal advice, financing advice, or a substitute for due diligence."
)


class ParcelBookLoginView(LoginView):
    template_name = "opportunity/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse("opportunity_home")


class ParcelBookLogoutView(LogoutView):
    next_page = reverse_lazy("opportunity_login")


@login_required(login_url=reverse_lazy("opportunity_login"))
def home(request):
    context = dashboard_context(request.user, sales_sort=request.GET.get("sales_sort", ""))
    context.update({"active_nav": "overview", "disclaimer": DISCLAIMER})
    return render(request, "opportunity/home.html", context)


@login_required(login_url=reverse_lazy("opportunity_login"))
def newsletter_preview(request):
    context = dashboard_context(request.user)
    context.update({"active_nav": "overview", "disclaimer": DISCLAIMER})
    return render(request, "opportunity/newsletter_preview.html", context)


@login_required(login_url=reverse_lazy("opportunity_login"))
def explore(request):
    selected_tab = request.GET.get("tab", DEFAULT_TAB)
    if selected_tab not in TAB_LOOKUP:
        selected_tab = DEFAULT_TAB

    filters = {key: request.GET.get(key, "") for key in FILTER_KEYS}
    view_mode = request.GET.get("view", "list")
    if view_mode == "table":
        view_mode = "list"
    elif view_mode == "cards":
        view_mode = "card"
    if view_mode not in {"list", "card", "map"}:
        view_mode = "list"

    page = _positive_int(request.GET.get("page"), 1)
    fetch_limit = page * PAGE_SIZE
    all_rows = mark_saved(fetch_tab_rows(selected_tab, filters, limit=fetch_limit), request.user)
    for row in all_rows:
        row["source_tab"] = selected_tab
    rows = all_rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    has_previous = page > 1
    has_next = len(all_rows) == fetch_limit
    counts = tab_counts(filters)

    return render(
        request,
        "opportunity/explore.html",
        {
            "active_nav": "opportunities",
            "active_tab": selected_tab,
            "tabs": TABS,
            "selected_tab": selected_tab,
            "selected_tab_obj": TAB_LOOKUP[selected_tab],
            "counts": counts,
            "rows": rows,
            "filters": filters,
            "view_mode": view_mode,
            "page": page,
            "has_previous": has_previous,
            "has_next": has_next,
            "previous_url": _page_url(selected_tab, page - 1, view_mode) if has_previous else "",
            "next_url": _page_url(selected_tab, page + 1, view_mode) if has_next else "",
            "disclaimer": DISCLAIMER,
        },
    )


@login_required(login_url=reverse_lazy("opportunity_login"))
def ai_search(request):
    error = ""
    prompt = ""
    if request.method == "POST":
        prompt = (request.POST.get("prompt") or "").strip()
        if not prompt:
            error = "Enter a natural-language search first."
        else:
            search = start_ai_opportunity_search(request.user, prompt)
            return redirect("opportunity_ai_search_detail", search_id=search.pk)

    return render(
        request,
        "opportunity/ai_search.html",
        {
            "active_nav": "ai_search",
            "prompt": prompt,
            "error": error,
            "recent_searches": recent_searches_for_user(request.user, limit=10),
            "saved_searches": saved_searches_for_user(request.user, limit=8),
            "disclaimer": DISCLAIMER,
        },
    )


@login_required(login_url=reverse_lazy("opportunity_login"))
def ai_search_detail(request, search_id):
    search = get_object_or_404(OpportunitySearch, pk=search_id, user=request.user)
    is_pending = search.status == OpportunitySearch.STATUS_DRAFT
    if is_pending:
        ensure_ai_search_worker(search)
    view_mode = _view_mode(request.GET.get("view", "list"))
    page = _positive_int(request.GET.get("page"), 1)
    all_rows = [] if is_pending else display_rows_for_search(search, request.user)
    for row in all_rows:
        row["ai_search"] = search
    rows = all_rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    has_previous = page > 1
    has_next = len(all_rows) > page * PAGE_SIZE
    return render(
        request,
        "opportunity/ai_search_detail.html",
        {
            "active_nav": "ai_search",
            "search": search,
            "rows": rows,
            "display_result_count": len(all_rows),
            "view_mode": view_mode,
            "page": page,
            "has_previous": has_previous,
            "has_next": has_next,
            "previous_url": _search_page_url(search, page - 1, view_mode) if has_previous else "",
            "next_url": _search_page_url(search, page + 1, view_mode) if has_next else "",
            "is_pending": is_pending,
            "feedback_reasons": FEEDBACK_REASONS,
            "disclaimer": DISCLAIMER,
        },
    )


@login_required(login_url=reverse_lazy("opportunity_login"))
@require_POST
def save_ai_search(request, search_id):
    search = get_object_or_404(OpportunitySearch, pk=search_id, user=request.user)
    search.mark_saved()
    return redirect("opportunity_ai_search_detail", search_id=search.pk)


@login_required(login_url=reverse_lazy("opportunity_login"))
@require_POST
def refresh_ai_search(request, search_id):
    search = get_object_or_404(OpportunitySearch, pk=search_id, user=request.user)
    search = start_refresh_opportunity_search(search)
    return redirect("opportunity_ai_search_detail", search_id=search.pk)


@login_required(login_url=reverse_lazy("opportunity_login"))
@require_POST
def ai_search_feedback(request, search_id):
    search = get_object_or_404(OpportunitySearch, pk=search_id, user=request.user)
    try:
        record_search_feedback(
            user=request.user,
            search=search,
            rating=request.POST.get("rating", ""),
            reason_code=request.POST.get("reason_code", ""),
            comment=request.POST.get("comment", ""),
            parcel_number=request.POST.get("parcel_number", ""),
        )
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    next_url = request.POST.get("next") or reverse("opportunity_ai_search_detail", args=[search.pk])
    return redirect(next_url)


@login_required(login_url=reverse_lazy("opportunity_login"))
def parcel(request, parcel_number):
    is_saved = OpportunitySavedParcel.objects.filter(user=request.user, parcel_number=parcel_number.upper()).exists()
    use_ai_feasibility = is_saved
    detail = parcel_detail(parcel_number, include_dossier=is_saved, use_ai_feasibility=use_ai_feasibility)
    if not detail:
        raise Http404("Parcel not found")
    detail["is_saved"] = is_saved
    detail["is_locked"] = not is_saved
    detail["ai_feasibility_requested"] = use_ai_feasibility
    detail["source_tab"] = ""
    return render(
        request,
        "opportunity/parcel_detail.html",
        {"active_nav": "opportunities", "parcel": detail, "disclaimer": DISCLAIMER},
    )


@login_required(login_url=reverse_lazy("opportunity_login"))
def watchlist(request):
    return render(
        request,
        "opportunity/watchlist.html",
        {
            "active_nav": "watchlist",
            "rows": watchlist_rows(request.user),
            "saved_searches": saved_searches_for_user(request.user),
            "sync": latest_assessor_sync_summary(request.user),
            "disclaimer": DISCLAIMER,
        },
    )


@login_required(login_url=reverse_lazy("opportunity_login"))
@require_POST
def save_parcel(request):
    parcel_number = (request.POST.get("parcel_number") or "").strip().upper()
    if not parcel_number:
        return HttpResponseBadRequest("Missing parcel_number")
    source_tab = (request.POST.get("source_tab") or "").strip()
    action = (request.POST.get("action") or "save").strip().lower()
    next_url = request.POST.get("next") or reverse("opportunity_home")
    if action == "unsave":
        OpportunitySavedParcel.objects.filter(user=request.user, parcel_number=parcel_number).delete()
    else:
        OpportunitySavedParcel.objects.update_or_create(
            user=request.user,
            parcel_number=parcel_number,
            defaults={"source_tab": source_tab},
        )
    return redirect(next_url)


@login_required(login_url=reverse_lazy("opportunity_login"))
def notification_settings(request):
    from .models import UserNotificationPreference

    pref, _ = UserNotificationPreference.objects.get_or_create(user=request.user)
    saved = False

    if request.method == "POST":
        cadence = request.POST.get("digest_cadence", UserNotificationPreference.CADENCE_DAILY)
        if cadence not in {UserNotificationPreference.CADENCE_DAILY, UserNotificationPreference.CADENCE_WEEKLY}:
            cadence = UserNotificationPreference.CADENCE_DAILY
        pref.notify_watchlist = request.POST.get("notify_watchlist") == "on"
        pref.digest_cadence = cadence
        pref.notify_brief = request.POST.get("notify_brief") == "on"
        pref.save()
        saved = True

    return render(
        request,
        "opportunity/settings.html",
        {
            "active_nav": "settings",
            "pref": pref,
            "saved": saved,
            "disclaimer": DISCLAIMER,
        },
    )


def staff_redirect(request):
    return redirect("opportunity_explore")


def _page_url(tab: str, page: int, view_mode: str) -> str:
    params = {"tab": tab, "page": page, "view": view_mode}
    return f"{reverse('opportunity_explore')}?{urlencode(params)}"


def _search_page_url(search: OpportunitySearch, page: int, view_mode: str) -> str:
    params = {"page": page, "view": view_mode}
    return f"{reverse('opportunity_ai_search_detail', args=[search.pk])}?{urlencode(params)}"


def _view_mode(value: str) -> str:
    if value == "cards":
        value = "card"
    if value not in {"list", "card", "map"}:
        return "list"
    return value


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
