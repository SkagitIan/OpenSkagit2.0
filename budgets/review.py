from __future__ import annotations

from collections import Counter

from .models import BudgetDocument, BudgetLineItem


class BudgetReviewError(ValueError):
    pass


def validate_document_for_publication(document: BudgetDocument) -> None:
    if not document.pages.exists():
        raise BudgetReviewError("Document has no extracted pages.")

    reviewed = document.line_items.filter(reviewed=True).exclude(side=BudgetLineItem.Side.OTHER)
    totals = reviewed.filter(is_total=True)
    if not totals.exists():
        raise BudgetReviewError("Document has no reviewed total.")

    duplicate_sides = [
        side
        for side, count in Counter(totals.values_list("side", flat=True)).items()
        if count > 1
    ]
    if duplicate_sides:
        raise BudgetReviewError(
            "Document has more than one reviewed total for: " + ", ".join(sorted(duplicate_sides)) + "."
        )

    uncited = reviewed.filter(page_number__isnull=True)
    if uncited.exists():
        raise BudgetReviewError("Every reviewed row must cite a PDF page.")

    invalid_pages = reviewed.filter(page_number__gt=document.page_count)
    if invalid_pages.exists():
        raise BudgetReviewError("A reviewed row cites a page beyond the PDF page count.")

    if reviewed.filter(raw_data__candidate_only=True).exists():
        raise BudgetReviewError("Raw extraction candidates cannot be published as reviewed data.")
