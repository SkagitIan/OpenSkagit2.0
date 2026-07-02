from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from parcelbook.ai.ask import ask_parcels
from parcelbook.ai.parcel_query_planner import plan_parcel_query
from parcelbook.ai.sql_safety import validate_select_sql

EXAMPLE_QUERIES = [
    "Find possible ADU candidates in Mount Vernon.",
    "Show me city parcels with older small homes on larger lots.",
    "Find rural residential parcels between 2 and 10 acres with older homes.",
    "Show me properties that already appear to have a secondary detached unit.",
    "Find parcels in Sedro-Woolley with no recent sale and moderate assessed value.",
]


@staff_member_required
def staff_query_lab(request):
    query = (request.POST.get("query") or request.GET.get("query") or "").strip()
    mode = request.POST.get("mode") or request.GET.get("mode") or "plan"
    context = {
        "query": query,
        "mode": mode,
        "examples": EXAMPLE_QUERIES,
    }
    if query:
        try:
            if mode == "run":
                context["result"] = ask_parcels(query)
            else:
                plan = plan_parcel_query(query)
                context["plan"] = plan
                context["safe_sql"] = validate_select_sql(plan.sql, limit=25)
        except Exception as exc:  # Keep staff lab errors visible and non-fatal.
            context["error"] = str(exc)
    return render(request, "parcelbook/query_lab.html", context)
