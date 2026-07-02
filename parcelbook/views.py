from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from parcelbook_ai.schema_guide import get_parcel_search_semantic_guide
from parcelbook_ai.service import ask_parcels
from parcelbook_ai.zoning_router import detect_zoning_need

EXAMPLE_QUERIES = [
    "Find older houses on big lots in Sedro-Woolley that haven’t sold recently.",
    "Find ADU candidates in Mount Vernon.",
    "Which zones allow restaurants?",
    "Find parcels in zones where restaurants are allowed.",
]


@staff_member_required
def staff_query_lab(request):
    query = (request.POST.get("query") or request.GET.get("query") or "").strip()
    limit = _parse_limit(request.POST.get("limit") or request.GET.get("limit"))
    context = {
        "query": query,
        "limit": limit,
        "examples": EXAMPLE_QUERIES,
        "schema_guide": get_parcel_search_semantic_guide(),
    }
    if query:
        try:
            context["zoning_route"] = detect_zoning_need(query)
            if request.method == "POST":
                context["answer"] = ask_parcels(query, limit=limit)
        except Exception as exc:  # Keep the staff test UI non-fatal.
            context["error"] = str(exc)
    return render(request, "parcelbook/query_lab.html", context)


def _parse_limit(raw_limit: str | None) -> int:
    try:
        return max(1, min(int(raw_limit or 10), 100))
    except (TypeError, ValueError):
        return 10
