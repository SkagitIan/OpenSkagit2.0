from __future__ import annotations

import ast
import operator
from decimal import Decimal
from typing import Any

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank, SearchVector
from django.db.models import Sum

from .models import BudgetDocument, BudgetDocumentPage, BudgetJurisdiction, BudgetLineItem


STATUS_PRIORITY = {
    BudgetDocument.Status.AMENDED: 4,
    BudgetDocument.Status.ADOPTED: 3,
    BudgetDocument.Status.PRELIMINARY: 2,
    BudgetDocument.Status.PROPOSED: 1,
}

MAX_READ_PAGES = 5
SEARCH_CONFIG = "english"


def _money(value: Decimal | None) -> float:
    return float(value or 0)


def _jurisdiction_payload(row: BudgetJurisdiction) -> dict[str, Any]:
    documents = row.budget_documents.all()
    published_years = list(
        documents.filter(published=True)
        .order_by("-fiscal_year")
        .values_list("fiscal_year", flat=True)
        .distinct()
    )
    return {
        "slug": row.slug,
        "name": row.name,
        "mcag": row.mcag,
        "kind": row.kind,
        "published_years": published_years,
        "coverage_status": (
            "published"
            if published_years
            else "under_review"
            if documents.exists()
            else "no_current_source"
        ),
        "population": row.population,
        "population_source": row.population_source,
        "population_source_year": row.population_source_year,
        "population_source_url": row.population_source_url,
    }


def _document_payload(document: BudgetDocument) -> dict[str, Any]:
    return {
        "id": document.pk,
        "title": document.title,
        "fiscal_year": document.fiscal_year,
        "status": document.status,
        "status_label": document.get_status_display(),
        "version_date": document.version_date.isoformat() if document.version_date else None,
        "adopted_on": document.adopted_on.isoformat() if document.adopted_on else None,
        "source_url": document.source_url,
        "page_count": document.page_count,
    }


def _resolve_jurisdiction(value: str) -> BudgetJurisdiction:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("A jurisdiction is required.")
    rows = list(BudgetJurisdiction.objects.filter(active=True))
    exact = [row for row in rows if normalized in {row.slug.lower(), row.name.lower(), row.mcag.lower()}]
    if exact:
        return exact[0]
    partial = [row for row in rows if normalized in row.name.lower() or normalized in row.slug.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ValueError(f"No budget jurisdiction matched {value!r}.")
    raise ValueError(f"Jurisdiction {value!r} is ambiguous; use a full name or slug.")


def _select_document(jurisdiction: BudgetJurisdiction, year: int | None = None) -> BudgetDocument:
    queryset = BudgetDocument.objects.filter(jurisdiction=jurisdiction, published=True)
    if year is not None:
        queryset = queryset.filter(fiscal_year=year)
    documents = list(queryset)
    authoritative = [row for row in documents if row.status in {BudgetDocument.Status.ADOPTED, BudgetDocument.Status.AMENDED}]
    if authoritative:
        documents = authoritative
    if not documents:
        suffix = f" for {year}" if year else ""
        raise ValueError(f"No reviewed, published budget document is available for {jurisdiction.name}{suffix}.")
    documents.sort(
        key=lambda row: (
            bool(row.is_current),
            row.fiscal_year,
            STATUS_PRIORITY.get(row.status, 0),
            row.version_date or row.adopted_on or row.imported_at.date(),
            row.pk,
        ),
        reverse=True,
    )
    return documents[0]


def budget_list_jurisdictions() -> dict[str, Any]:
    rows = []
    for jurisdiction in BudgetJurisdiction.objects.filter(active=True):
        rows.append(_jurisdiction_payload(jurisdiction))
    return {"jurisdictions": rows}


def budget_get_summary(jurisdiction: str, year: int | None = None) -> dict[str, Any]:
    owner = _resolve_jurisdiction(jurisdiction)
    document = _select_document(owner, year)
    total_rows = document.line_items.filter(reviewed=True, is_total=True).exclude(side=BudgetLineItem.Side.OTHER)
    totals = {
        row["side"]: _money(row["total"])
        for row in total_rows.values("side").annotate(total=Sum("amount"))
    }
    revenue = totals.get(BudgetLineItem.Side.REVENUE)
    expenditure = totals.get(BudgetLineItem.Side.EXPENDITURE)
    citations = [
        {
            "side": row.side,
            "page": row.page_number,
            "source_url": document.source_url,
            "note": row.source_note,
        }
        for row in total_rows.order_by("side", "display_order", "id")
    ]
    return {
        "jurisdiction": _jurisdiction_payload(owner),
        "document": _document_payload(document),
        "totals": {
            "revenue": revenue,
            "expenditure": expenditure,
            "difference": revenue - expenditure if revenue is not None and expenditure is not None else None,
            "fund_balance": totals.get(BudgetLineItem.Side.FUND_BALANCE, 0),
        },
        "line_item_count": document.line_items.filter(reviewed=True, is_total=False).exclude(side=BudgetLineItem.Side.OTHER).count(),
        "source_pages": list(
            total_rows.exclude(page_number__isnull=True)
            .order_by("page_number")
            .values_list("page_number", flat=True)
            .distinct()
        ),
        "citations": citations,
        "review_notes": (document.extracted_summary or {}).get("review_notes", []),
        "warning": "Revenue minus expenditure is not automatically a surplus or change in fund balance.",
    }


def budget_get_breakdown(
    jurisdiction: str,
    year: int | None = None,
    side: str = BudgetLineItem.Side.EXPENDITURE,
    group_by: str = "auto",
    limit: int = 20,
) -> dict[str, Any]:
    if side not in {BudgetLineItem.Side.REVENUE, BudgetLineItem.Side.EXPENDITURE, BudgetLineItem.Side.FUND_BALANCE}:
        raise ValueError("side must be revenue, expenditure, or fund_balance.")
    fields = {
        "fund": ("fund_code", "fund_name"),
        "department": ("department_code", "department_name"),
        "account": ("account_code", "account_name"),
        "category": (None, "category_name"),
    }
    if group_by not in {*fields, "auto"}:
        raise ValueError("group_by must be auto, fund, department, account, or category.")
    owner = _resolve_jurisdiction(jurisdiction)
    document = _select_document(owner, year)
    detail_rows = document.line_items.filter(reviewed=True, is_total=False, side=side)
    if group_by == "auto":
        group_by = next(
            (
                candidate
                for candidate, (_, field_name) in fields.items()
                if detail_rows.exclude(**{field_name: ""}).exists()
            ),
            "category",
        )
    code_field, name_field = fields[group_by]
    value_fields = [name_field] if code_field is None else [code_field, name_field]
    rows = (
        detail_rows.values(*value_fields)
        .annotate(amount=Sum("amount"))
        .order_by("-amount")[: max(1, min(limit, 100))]
    )
    side_total = document.line_items.filter(
        reviewed=True, is_total=True, side=side
    ).aggregate(total=Sum("amount"))["total"]
    result_rows = []
    for row in rows:
        item_filter = {name_field: row[name_field], "side": side, "reviewed": True, "is_total": False}
        if code_field is not None:
            item_filter[code_field] = row[code_field]
        matching = document.line_items.filter(**item_filter)
        pages = list(
            matching.exclude(page_number__isnull=True)
            .order_by("page_number")
            .values_list("page_number", flat=True)
            .distinct()
        )
        percent_of_side_total = (
            round(float(row["amount"]) / float(side_total) * 100, 1)
            if side_total
            else None
        )
        result_rows.append({
            "code": row[code_field] if code_field is not None else "",
            "name": row[name_field] or "Not categorized",
            "amount": _money(row["amount"]),
            "percent_of_side_total": percent_of_side_total,
            "pages": pages,
            "source_url": document.source_url,
            "notes": list(matching.exclude(source_note="").values_list("source_note", flat=True).distinct()),
        })
    return {
        "jurisdiction": _jurisdiction_payload(owner),
        "document": _document_payload(document),
        "side": side,
        "side_total": _money(side_total) if side_total is not None else None,
        "group_by": group_by,
        "rows": result_rows,
        "complete": side in (document.extracted_summary or {}).get("complete_breakdown_sides", []),
    }


def budget_get_trend(jurisdiction: str, side: str = BudgetLineItem.Side.EXPENDITURE) -> dict[str, Any]:
    owner = _resolve_jurisdiction(jurisdiction)
    years = owner.budget_documents.filter(published=True).values_list("fiscal_year", flat=True).distinct()
    rows = []
    for year in sorted(years):
        document = _select_document(owner, year)
        total = document.line_items.filter(reviewed=True, is_total=True, side=side).aggregate(total=Sum("amount"))["total"]
        rows.append({"year": year, "amount": _money(total) if total is not None else None, "document": _document_payload(document)})
    return {"jurisdiction": _jurisdiction_payload(owner), "side": side, "rows": rows}


def budget_compare_jurisdictions(jurisdictions: list[str], year: int | None = None, side: str = "expenditure") -> dict[str, Any]:
    if side not in {"revenue", "expenditure", "fund_balance"}:
        raise ValueError("side must be revenue, expenditure, or fund_balance.")
    if not jurisdictions or len(jurisdictions) > 12:
        raise ValueError("Provide between 1 and 12 jurisdictions.")
    rows = []
    for value in jurisdictions:
        summary = budget_get_summary(value, year)
        amount = summary["totals"].get(side)
        rows.append(
            {
                "jurisdiction": summary["jurisdiction"],
                "year": summary["document"]["fiscal_year"],
                "status": summary["document"]["status"],
                "amount": amount,
                "available": amount is not None,
                "source_url": summary["document"]["source_url"],
                "citations": [item for item in summary["citations"] if item["side"] == side],
            }
        )
    return {
        "side": side,
        "rows": sorted(rows, key=lambda row: (row["available"], row["amount"] or 0), reverse=True),
    }


def _search_pages(document: BudgetDocument, query: str, limit: int) -> list[dict[str, Any]]:
    search_query = SearchQuery(query, config=SEARCH_CONFIG, search_type="websearch")
    vector = SearchVector("text", config=SEARCH_CONFIG)
    rows = (
        BudgetDocumentPage.objects.filter(document=document)
        .annotate(
            search=vector,
            rank=SearchRank(vector, search_query),
            headline=SearchHeadline(
                "text",
                search_query,
                config=SEARCH_CONFIG,
                start_sel="",
                stop_sel="",
                max_words=60,
                min_words=25,
                max_fragments=1,
            ),
        )
        # `ts_rank` floors near-zero (Postgres returns ~1e-20, not exactly 0) even for
        # non-matching rows, so filter on the actual `@@` match rather than rank > 0.
        .filter(search=search_query)
        .order_by("-rank", "page_number")[: max(1, min(limit, 20))]
    )
    return [
        {
            "page": row.page_number,
            "rank": round(float(row.rank), 4),
            "snippet": " ".join(row.headline.split()),
        }
        for row in rows
    ]


def budget_search_documents(jurisdiction: str, query: str, year: int | None = None, limit: int = 8) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("Use at least one descriptive search term.")
    owner = _resolve_jurisdiction(jurisdiction)
    document = _select_document(owner, year)
    matches = _search_pages(document, query, limit)
    return {
        "jurisdiction": _jurisdiction_payload(owner),
        "document": _document_payload(document),
        "query": query,
        "matches": matches,
    }


def budget_search_all_documents(query: str, year: int | None = None, limit_per_jurisdiction: int = 4) -> dict[str, Any]:
    """Full-text search across every published jurisdiction's official budget document at once."""
    if not query.strip():
        raise ValueError("Use at least one descriptive search term.")
    jurisdictions_searched = []
    results = []
    for owner in BudgetJurisdiction.objects.filter(active=True):
        try:
            document = _select_document(owner, year)
        except ValueError:
            continue
        jurisdictions_searched.append(owner.name)
        matches = _search_pages(document, query, limit_per_jurisdiction)
        if matches:
            results.append({
                "jurisdiction": _jurisdiction_payload(owner),
                "document": _document_payload(document),
                "matches": matches,
            })
    results.sort(key=lambda row: max((m["rank"] for m in row["matches"]), default=0), reverse=True)
    return {
        "query": query,
        "jurisdictions_searched": jurisdictions_searched,
        "results": results,
    }


def budget_read_pages(jurisdiction: str, start_page: int, end_page: int, year: int | None = None) -> dict[str, Any]:
    """Return full official page text for a small page range so the agent can read past a search snippet."""
    owner = _resolve_jurisdiction(jurisdiction)
    document = _select_document(owner, year)
    if start_page < 1 or end_page < start_page:
        raise ValueError("start_page must be at least 1 and end_page must not be before start_page.")
    if document.page_count and start_page > document.page_count:
        raise ValueError(f"{owner.name}'s {document.fiscal_year} document has only {document.page_count} pages.")
    capped_end = min(end_page, start_page + MAX_READ_PAGES - 1, document.page_count or end_page)
    pages = list(
        BudgetDocumentPage.objects.filter(
            document=document, page_number__gte=start_page, page_number__lte=capped_end
        ).order_by("page_number")
    )
    if not pages:
        raise ValueError(
            f"No extracted page text for {owner.name} pages {start_page}-{capped_end}. "
            f"The document has {document.page_count} pages."
        )
    return {
        "jurisdiction": _jurisdiction_payload(owner),
        "document": _document_payload(document),
        "requested_range": [start_page, end_page],
        "returned_range": [pages[0].page_number, pages[-1].page_number],
        "capped": capped_end < end_page,
        "pages": [{"page": page.page_number, "text": page.text} for page in pages],
    }


def budget_compare_per_capita(
    jurisdictions: list[str], year: int | None = None, side: str = "expenditure"
) -> dict[str, Any]:
    """Compare reviewed totals per resident, citing the population source and vintage for each jurisdiction."""
    comparison = budget_compare_jurisdictions(jurisdictions, year, side)
    rows = []
    for row in comparison["rows"]:
        jurisdiction = row["jurisdiction"]
        population = jurisdiction.get("population")
        per_capita = (
            round(row["amount"] / population, 2)
            if row["available"] and population
            else None
        )
        rows.append({
            **row,
            "population": population,
            "population_source": jurisdiction.get("population_source"),
            "population_source_year": jurisdiction.get("population_source_year"),
            "per_capita": per_capita,
        })
    return {
        "side": side,
        "rows": sorted(rows, key=lambda row: (row["per_capita"] is not None, row["per_capita"] or 0), reverse=True),
    }


_SAFE_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SAFE_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("Only numbers are allowed in an expression.")
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BIN_OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        try:
            return _SAFE_BIN_OPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise ValueError("Division by zero.") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY_OPS:
        return _SAFE_UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Expression may only contain numbers, + - * / // % **, and parentheses.")


def calculate(expression: str) -> dict[str, Any]:
    """Safely evaluate an arithmetic expression (numbers and + - * / // % ** only) so the agent never does mental math."""
    if not expression or len(expression) > 200:
        raise ValueError("Provide a short arithmetic expression, e.g. '115485921 / 17565'.")
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Could not evaluate {expression!r}: {exc}") from exc
    return {"expression": expression, "result": result}


def homepage_context(
    selected: str | None = None,
    year: int | None = None,
    breakdown_group_by: str = "auto",
    breakdown_limit: int = 10,
) -> dict[str, Any]:
    jurisdictions = list(BudgetJurisdiction.objects.filter(active=True))
    for item in jurisdictions:
        item.has_published_budget = item.budget_documents.filter(published=True).exists()
        item.has_imported_budget = item.budget_documents.exists()
    selected_row = None
    summary = None
    breakdown = None
    error = None
    if selected:
        try:
            selected_row = _resolve_jurisdiction(selected)
            summary = budget_get_summary(selected_row.slug, year)
            breakdown = budget_get_breakdown(selected_row.slug, year, group_by=breakdown_group_by, limit=breakdown_limit)
        except ValueError as exc:
            error = str(exc)
    return {
        "jurisdictions": jurisdictions,
        "selected_jurisdiction": selected_row,
        "summary": summary,
        "breakdown": breakdown,
        "error": error,
    }
