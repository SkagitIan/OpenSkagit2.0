from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from budgets.models import BudgetDocument, BudgetLineItem
from budgets.review import BudgetReviewError, validate_document_for_publication


DEFAULT_DATA = Path(settings.BASE_DIR) / "data" / "budget_reviewed_2026.json"
AMOUNT_KIND_BY_STATUS = {
    BudgetDocument.Status.PROPOSED: BudgetLineItem.AmountKind.REQUESTED,
    BudgetDocument.Status.PRELIMINARY: BudgetLineItem.AmountKind.RECOMMENDED,
    BudgetDocument.Status.ADOPTED: BudgetLineItem.AmountKind.ADOPTED,
    BudgetDocument.Status.AMENDED: BudgetLineItem.AmountKind.AMENDED,
}


class Command(BaseCommand):
    help = "Validate and load the versioned, human-reviewed budget facts; optionally publish them."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_DATA))
        parser.add_argument("--jurisdiction", action="append", dest="jurisdictions")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--publish", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()
        if not path.is_file():
            raise CommandError(f"Reviewed budget data not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read reviewed budget data: {exc}") from exc

        selected = set(options["jurisdictions"] or [])
        records = [
            row for row in payload.get("documents", [])
            if not selected or row.get("jurisdiction") in selected
        ]
        if not records:
            raise CommandError("No reviewed budget records matched the selection.")

        prepared = [
            self._prepare(record, payload.get("version", ""), payload.get("reviewed_on", ""))
            for record in records
        ]
        if options["dry_run"]:
            for document, items, summary in prepared:
                self.stdout.write(
                    f"{document.jurisdiction.slug}: {len(items)} reviewed rows; "
                    f"totals={summary['reviewed_totals']}"
                )
            self.stdout.write(self.style.SUCCESS(f"Dry run passed for {len(prepared)} document(s)."))
            return

        with transaction.atomic():
            for document, items, summary in prepared:
                document.line_items.filter(reviewed=True).delete()
                BudgetLineItem.objects.bulk_create(items, batch_size=500)
                merged = dict(document.extracted_summary or {})
                merged.update(summary)
                document.extracted_summary = merged
                document.reviewed_at = timezone.now()
                document.published = False
                document.save(update_fields=["extracted_summary", "reviewed_at", "published"])

                if options["publish"]:
                    try:
                        validate_document_for_publication(document)
                    except BudgetReviewError as exc:
                        raise CommandError(f"{document}: {exc}") from exc
                    BudgetDocument.objects.filter(jurisdiction=document.jurisdiction).exclude(pk=document.pk).update(
                        is_current=False
                    )
                    document.is_current = True
                    document.published = True
                    document.save(update_fields=["is_current", "published"])

        verb = "Published" if options["publish"] else "Loaded"
        self.stdout.write(self.style.SUCCESS(f"{verb} reviewed data for {len(prepared)} document(s)."))

    def _prepare(self, record, review_version, reviewed_on):
        required = {"jurisdiction", "fiscal_year", "status", "content_sha256", "rows"}
        missing = sorted(required - set(record))
        if missing:
            raise CommandError("Reviewed record missing fields: " + ", ".join(missing))
        try:
            document = BudgetDocument.objects.select_related("jurisdiction").get(
                jurisdiction__slug=record["jurisdiction"],
                fiscal_year=int(record["fiscal_year"]),
                status=record["status"],
                content_sha256=record["content_sha256"],
            )
        except BudgetDocument.DoesNotExist as exc:
            raise CommandError(
                f"Imported PDF does not match reviewed source for {record['jurisdiction']} "
                f"{record['fiscal_year']}."
            ) from exc
        except BudgetDocument.MultipleObjectsReturned as exc:
            raise CommandError(f"Multiple imported PDFs match {record['jurisdiction']}.") from exc

        items = []
        totals = {}
        detail_sums = {}
        for order, row in enumerate(record["rows"], 1):
            side = str(row.get("side", "")).strip()
            if side not in {
                BudgetLineItem.Side.REVENUE,
                BudgetLineItem.Side.EXPENDITURE,
                BudgetLineItem.Side.FUND_BALANCE,
            }:
                raise CommandError(f"{record['jurisdiction']} row {order}: invalid side {side!r}.")
            try:
                amount = Decimal(str(row["amount"]))
                page_number = int(row["page_number"])
            except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
                raise CommandError(
                    f"{record['jurisdiction']} row {order}: invalid amount or page."
                ) from exc
            if page_number < 1 or page_number > document.page_count:
                raise CommandError(
                    f"{record['jurisdiction']} row {order}: page {page_number} is outside the PDF."
                )
            is_total = bool(row.get("is_total", False))
            if is_total:
                if side in totals:
                    raise CommandError(f"{record['jurisdiction']}: duplicate {side} total.")
                totals[side] = amount
            else:
                detail_sums[side] = detail_sums.get(side, Decimal("0")) + amount

            scope = str(row.get("scope", "")).strip()
            if not scope:
                scope = "fund" if row.get("fund_name") else "category"
            items.append(
                BudgetLineItem(
                    document=document,
                    page_number=page_number,
                    fiscal_year=document.fiscal_year,
                    side=side,
                    amount_kind=AMOUNT_KIND_BY_STATUS.get(
                        document.status, BudgetLineItem.AmountKind.UNKNOWN
                    ),
                    fund_code=str(row.get("fund_code", "")).strip(),
                    fund_name=str(row.get("fund_name", "")).strip(),
                    department_code=str(row.get("department_code", "")).strip(),
                    department_name=str(row.get("department_name", "")).strip(),
                    account_code=str(row.get("account_code", "")).strip(),
                    account_name=str(row.get("account_name", "")).strip(),
                    category_name=str(row.get("category_name", "")).strip(),
                    amount=amount,
                    scope=scope,
                    is_total=is_total,
                    reviewed=True,
                    display_order=order,
                    source_note=str(row.get("source_note", "")).strip(),
                    raw_label=str(row.get("raw_label", "")).strip(),
                    raw_data={
                        "reviewed": True,
                        "review_version": review_version,
                        "source_page": page_number,
                    },
                )
            )

        if not totals:
            raise CommandError(f"{record['jurisdiction']}: at least one reviewed total is required.")
        tolerance = Decimal(str(record.get("breakdown_tolerance", "0")))
        complete_sides = record.get("complete_breakdown_sides", [])
        for side in complete_sides:
            if side not in totals:
                raise CommandError(f"{record['jurisdiction']}: complete {side} breakdown has no total.")
            variance = abs(totals[side] - detail_sums.get(side, Decimal("0")))
            if variance > tolerance:
                raise CommandError(
                    f"{record['jurisdiction']}: {side} detail differs from total by {variance}."
                )

        summary = {
            "review_required": False,
            "review_version": review_version,
            "reviewed_on": str(reviewed_on),
            "reviewed_line_item_count": len(items),
            "reviewed_totals": {side: float(amount) for side, amount in totals.items()},
            "complete_breakdown_sides": complete_sides,
            "review_notes": record.get("review_notes", []),
        }
        return document, items, summary
