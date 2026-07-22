from __future__ import annotations

import re

from django.http import HttpResponseNotAllowed
from django.shortcuts import render

from core.views import CITY_PAGES

from .agent import answer_budget_turn
from .models import BudgetDocument
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


def _decorate(context):
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
        for row in breakdown["rows"]:
            row["amount_display"] = _money_display(row["amount"])
            row["bar_width"] = round(100 * max(row["amount"], 0) / maximum, 1) if maximum else 0
    context["sample_questions"] = SAMPLE_QUESTIONS
    context["breakdown_label"] = {
        "fund": "funds",
        "department": "departments",
        "account": "accounts",
        "category": "categories",
    }.get((breakdown or {}).get("group_by"), "categories")
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
    return render(request, "budgets/home.html", _decorate(homepage_context(jurisdiction, year)))


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
    if not question:
        answer = "What would you like to know about the budget?"
    elif not selected:
        answer = "Which jurisdiction do you mean? Choose one above, then ask again."
    elif not summary:
        answer = context.get("error") or "No reviewed, published budget is available for that selection."
    else:
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
