from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from budgets.models import BudgetDocument, BudgetLineItem


FIELDS = {
    "side", "amount", "amount_kind", "page_number", "fiscal_year",
    "fund_code", "fund_name", "department_code", "department_name",
    "account_code", "account_name", "category_name", "scope", "is_total",
    "display_order", "source_note", "raw_label",
}


class Command(BaseCommand):
    help = "Load reviewed, normalized budget line items from CSV into a draft document."

    def add_arguments(self, parser):
        parser.add_argument("--document", required=True, type=int)
        parser.add_argument("--csv", required=True)
        parser.add_argument("--replace", action="store_true")

    def handle(self, *args, **options):
        try:
            document = BudgetDocument.objects.get(pk=options["document"])
        except BudgetDocument.DoesNotExist as exc:
            raise CommandError("Budget document not found.") from exc
        path = Path(options["csv"]).resolve()
        if not path.is_file():
            raise CommandError(f"CSV not found: {path}")
        rows = self._read_rows(path, document)
        with transaction.atomic():
            if options["replace"]:
                document.line_items.filter(reviewed=True).delete()
            BudgetLineItem.objects.bulk_create(rows, batch_size=500)
            totals = {
                row["side"]: float(row["total"] or 0)
                for row in document.line_items.filter(reviewed=True, is_total=True).exclude(side=BudgetLineItem.Side.OTHER)
                .values("side").annotate(total=Sum("amount"))
            }
            summary = dict(document.extracted_summary or {})
            summary.update({"reviewed_line_item_count": document.line_items.filter(reviewed=True).exclude(side=BudgetLineItem.Side.OTHER).count(), "reviewed_totals": totals})
            document.extracted_summary = summary
            document.save(update_fields=["extracted_summary"])
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} reviewed line items into draft document {document.pk}."))

    def _read_rows(self, path: Path, document: BudgetDocument) -> list[BudgetLineItem]:
        items = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not {"side", "amount"}.issubset(reader.fieldnames):
                raise CommandError("CSV must include side and amount columns.")
            unknown = set(reader.fieldnames) - FIELDS
            if unknown:
                raise CommandError("Unknown CSV columns: " + ", ".join(sorted(unknown)))
            for line_number, row in enumerate(reader, 2):
                side = (row.get("side") or "").strip().lower()
                if side not in {BudgetLineItem.Side.REVENUE, BudgetLineItem.Side.EXPENDITURE, BudgetLineItem.Side.FUND_BALANCE}:
                    raise CommandError(f"Line {line_number}: invalid side {side!r}.")
                amount_kind = (row.get("amount_kind") or document.status).strip().lower()
                if amount_kind not in BudgetLineItem.AmountKind.values:
                    amount_kind = BudgetLineItem.AmountKind.UNKNOWN
                try:
                    amount = Decimal((row.get("amount") or "").replace("$", "").replace(",", ""))
                    page_number = int(row["page_number"]) if row.get("page_number") else None
                    fiscal_year = int(row.get("fiscal_year") or document.fiscal_year)
                    display_order = int(row.get("display_order") or 0)
                except (InvalidOperation, ValueError) as exc:
                    raise CommandError(f"Line {line_number}: invalid amount, page, or year.") from exc
                if page_number and document.page_count and page_number > document.page_count:
                    raise CommandError(f"Line {line_number}: page {page_number} exceeds the document page count.")
                items.append(BudgetLineItem(
                    document=document, page_number=page_number, fiscal_year=fiscal_year,
                    side=side, amount_kind=amount_kind, amount=amount,
                    fund_code=(row.get("fund_code") or "").strip(), fund_name=(row.get("fund_name") or "").strip(),
                    department_code=(row.get("department_code") or "").strip(), department_name=(row.get("department_name") or "").strip(),
                    account_code=(row.get("account_code") or "").strip(), account_name=(row.get("account_name") or "").strip(),
                    category_name=(row.get("category_name") or "").strip(), scope=(row.get("scope") or "").strip(),
                    is_total=(row.get("is_total") or "").strip().lower() in {"1", "true", "yes"},
                    reviewed=True, display_order=display_order,
                    source_note=(row.get("source_note") or "").strip(),
                    raw_label=(row.get("raw_label") or "").strip(),
                    raw_data={"reviewed": True, "reviewed_csv": path.name},
                ))
        if not items:
            raise CommandError("CSV contains no line items.")
        return items
