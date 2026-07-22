from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from .models import BudgetDocument, BudgetDocumentPage, BudgetJurisdiction, BudgetLineItem


STATUS_PRIORITY = {
    BudgetDocument.Status.AMENDED: 4,
    BudgetDocument.Status.ADOPTED: 3,
    BudgetDocument.Status.PRELIMINARY: 2,
    BudgetDocument.Status.PROPOSED: 1,
}


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
            "fund_balance": totals.get(BudgetLineItem.Side.FUND_BALANCE),
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
        result_rows.append({
            "code": row[code_field] if code_field is not None else "",
            "name": row[name_field] or "Not categorized",
            "amount": _money(row["amount"]),
            "pages": pages,
            "source_url": document.source_url,
            "notes": list(matching.exclude(source_note="").values_list("source_note", flat=True).distinct()),
        })
    return {
        "jurisdiction": _jurisdiction_payload(owner),
        "document": _document_payload(document),
        "side": side,
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


def budget_search_documents(jurisdiction: str, query: str, year: int | None = None, limit: int = 8) -> dict[str, Any]:
    owner = _resolve_jurisdiction(jurisdiction)
    document = _select_document(owner, year)
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2][:8]
    if not tokens:
        raise ValueError("Use at least one descriptive search term.")
    matches = []
    for page in BudgetDocumentPage.objects.filter(document=document).iterator():
        lowered = page.text.lower()
        score = sum(lowered.count(token) for token in tokens)
        if not score:
            continue
        position = min((lowered.find(token) for token in tokens if token in lowered), default=0)
        start = max(0, position - 180)
        end = min(len(page.text), position + 420)
        snippet = " ".join(page.text[start:end].split())
        matches.append({"page": page.page_number, "score": score, "snippet": snippet})
    matches.sort(key=lambda row: (-row["score"], row["page"]))
    return {
        "jurisdiction": _jurisdiction_payload(owner),
        "document": _document_payload(document),
        "query": query,
        "matches": matches[: max(1, min(limit, 20))],
    }


def homepage_context(selected: str | None = None, year: int | None = None) -> dict[str, Any]:
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
            breakdown = budget_get_breakdown(selected_row.slug, year, limit=10)
        except ValueError as exc:
            error = str(exc)
    return {
        "jurisdictions": jurisdictions,
        "selected_jurisdiction": selected_row,
        "summary": summary,
        "breakdown": breakdown,
        "error": error,
    }
