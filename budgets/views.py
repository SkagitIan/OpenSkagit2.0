from __future__ import annotations

from django.http import HttpResponseNotAllowed
from django.shortcuts import render

from core.views import CITY_PAGES

from .agent import answer_budget_question
from .models import BudgetDocument
from .services import homepage_context


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
    year = _year(request.POST.get("year"))
    context = _decorate(homepage_context(jurisdiction, year))
    context.update({"question": question, "answer": answer_budget_question(question, jurisdiction, year)})
    return render(request, "budgets/home.html", context)
