from __future__ import annotations

import json
import re

from django.http import HttpResponseNotAllowed, StreamingHttpResponse
from django.shortcuts import render

from core.views import CITY_PAGES

from . import services
from .agent import answer_budget_turn, stream_budget_turn
from .models import BudgetDocument, BudgetJurisdiction
from .services import homepage_context


JURISDICTION_ALIASES = {
    "skagit-county": ("skagit county", "county of skagit", "skagit"),
    "anacortes": ("anacortes",),
    "burlington": ("burlington",),
    "mount-vernon": ("mount vernon", "mt vernon"),
    "sedro-woolley": ("sedro-woolley", "sedro woolley", "sedro"),
    "concrete": ("town of concrete", "concrete"),
    "hamilton": ("town of hamilton", "hamilton"),
    "la-conner": ("la conner", "laconner"),
    "lyman": ("town of lyman", "lyman"),
}

BREAKDOWN_GROUPINGS = ("fund", "department", "category", "account")
BREAKDOWN_FETCH_LIMIT = 50
BREAKDOWN_VISIBLE_LIMIT = 10


def _jurisdiction_from_question(question: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", question.casefold()).strip()
    matches = {
        slug
        for slug, aliases in JURISDICTION_ALIASES.items()
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases)
    }
    return next(iter(matches)) if len(matches) == 1 else ""


SAMPLE_QUESTIONS = [
    "How much is budgeted for public safety?",
    "What are the largest spending departments?",
    "How much revenue is expected, and where does it come from?",
    "What changed from the prior year?",
    "What does the budget say about staffing?",
    "Which funds pay for capital projects?",
]


def _year(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _money_display(value) -> str:
    if value is None:
        return "Not separately stated"
    return f"-${abs(value):,.0f}" if value < 0 else f"${value:,.0f}"


def _decorate(context, group_by: str = "auto"):
    summary = context.get("summary")
    if summary:
        totals = summary["totals"]
        summary["totals_display"] = {
            key: _money_display(value)
            for key, value in totals.items()
        }
    breakdown = context.get("breakdown")
    if breakdown:
        maximum = max((row["amount"] for row in breakdown["rows"]), default=0)
        for index, row in enumerate(breakdown["rows"]):
            row["amount_display"] = _money_display(row["amount"])
            row["bar_width"] = round(100 * max(row["amount"], 0) / maximum, 1) if maximum else 0
            row["percent_display"] = (
                f"{row['percent_of_side_total']:.1f}%" if row.get("percent_of_side_total") is not None else "—"
            )
            row["is_extra"] = index >= BREAKDOWN_VISIBLE_LIMIT
    context["sample_questions"] = SAMPLE_QUESTIONS
    context["breakdown_label"] = {
        "fund": "funds",
        "department": "departments",
        "account": "accounts",
        "category": "categories",
    }.get((breakdown or {}).get("group_by"), "categories")
    context["breakdown_groupings"] = BREAKDOWN_GROUPINGS
    context["breakdown_group_by"] = group_by
    context["city_pages"] = CITY_PAGES
    selected = context.get("selected_jurisdiction")
    context["available_years"] = list(
        BudgetDocument.objects.filter(jurisdiction=selected, published=True)
        .order_by("-fiscal_year")
        .values_list("fiscal_year", flat=True)
        .distinct()
    ) if selected else []
    return context


def budget_home(request):
    jurisdiction = request.GET.get("jurisdiction", "").strip()
    year = _year(request.GET.get("year"))
    group_by = request.GET.get("group_by", "auto").strip()
    if group_by not in {*BREAKDOWN_GROUPINGS, "auto"}:
        group_by = "auto"
    context = homepage_context(jurisdiction, year, breakdown_group_by=group_by, breakdown_limit=BREAKDOWN_FETCH_LIMIT)
    return render(request, "budgets/home.html", _decorate(context, group_by))


def _gate_message(question: str, selected, summary, error: str | None) -> str | None:
    """Return the citizen-facing message for a request that can't reach the agent, or None to proceed."""
    if not question:
        return "What would you like to know about the budget?"
    if not selected:
        return "Which jurisdiction do you mean? Choose one above, then ask again."
    if not summary:
        return error or "No reviewed, published budget is available for that selection."
    return None


def budget_ask(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    question = request.POST.get("question", "").strip()[:500]
    jurisdiction = request.POST.get("jurisdiction", "").strip()
    requested_year = _year(request.POST.get("year"))
    if not jurisdiction:
        jurisdiction = _jurisdiction_from_question(question)
    context = _decorate(homepage_context(jurisdiction, requested_year))
    selected = context.get("selected_jurisdiction")
    summary = context.get("summary")
    answer = _gate_message(question, selected, summary, context.get("error"))
    if answer is None:
        effective_year = requested_year or summary["document"]["fiscal_year"]
        context_key = f"{selected.slug}:{effective_year}"
        previous_response_id = (
            request.session.get("budget_previous_response_id")
            if request.session.get("budget_context") == context_key
            else None
        )
        answer, response_id = answer_budget_turn(
            question, selected.slug, effective_year, previous_response_id
        )
        request.session["budget_context"] = context_key
        if response_id:
            request.session["budget_previous_response_id"] = response_id
        else:
            request.session.pop("budget_previous_response_id", None)
    context.update({"question": question, "answer": answer})
    return render(request, "budgets/home.html", context)


def budget_ask_stream(request):
    """Server-Sent Events endpoint for the JS-enhanced chat thread.

    Conversation continuity (`previous_response_id`) is carried by the client and
    echoed back on each request, rather than stored server-side in the session --
    Django's SessionMiddleware persists the session before a StreamingHttpResponse's
    body is actually consumed, so session writes made during streaming would be lost.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    question = request.POST.get("question", "").strip()[:500]
    jurisdiction = request.POST.get("jurisdiction", "").strip()
    requested_year = _year(request.POST.get("year"))
    previous_response_id = request.POST.get("previous_response_id", "").strip() or None
    if not jurisdiction:
        jurisdiction = _jurisdiction_from_question(question)

    def event_stream():
        def emit(payload):
            return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

        context = homepage_context(jurisdiction, requested_year)
        selected = context.get("selected_jurisdiction")
        summary = context.get("summary")
        gate = _gate_message(question, selected, summary, context.get("error"))
        if gate is not None:
            yield emit({"type": "final", "answer": gate, "response_id": None})
            return
        effective_year = requested_year or summary["document"]["fiscal_year"]
        yield emit({"type": "context", "jurisdiction": selected.slug, "year": effective_year})
        for event in stream_budget_turn(question, selected.slug, effective_year, previous_response_id):
            yield emit(event)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def budget_compare(request):
    all_jurisdictions = list(BudgetJurisdiction.objects.filter(active=True))
    # Supports both the checkbox form (repeated ?jurisdictions=a&jurisdictions=b) and a
    # single shareable comma-joined value (?jurisdictions=a,b).
    selected_slugs = [
        slug.strip()
        for raw in request.GET.getlist("jurisdictions")
        for slug in raw.split(",")
        if slug.strip()
    ]
    side = request.GET.get("side", "expenditure").strip()
    if side not in {"revenue", "expenditure", "fund_balance"}:
        side = "expenditure"
    year = _year(request.GET.get("year"))
    comparison = None
    error = None
    if selected_slugs:
        try:
            comparison = services.budget_compare_per_capita(selected_slugs, year, side)
            for row in comparison["rows"]:
                row["amount_display"] = _money_display(row["amount"]) if row["available"] else "Not available"
                row["per_capita_display"] = _money_display(row["per_capita"]) if row["per_capita"] is not None else "—"
                row["population_display"] = f"{row['population']:,}" if row["population"] else "—"
        except ValueError as exc:
            error = str(exc)
    return render(request, "budgets/compare.html", {
        "jurisdictions": all_jurisdictions,
        "selected_slugs": selected_slugs,
        "side": side,
        "year": year,
        "comparison": comparison,
        "error": error,
        "city_pages": CITY_PAGES,
    })
