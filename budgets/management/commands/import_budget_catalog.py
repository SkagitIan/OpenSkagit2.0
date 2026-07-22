from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from budgets.models import BudgetDocument


class Command(BaseCommand):
    help = "Import verified official budget PDFs from data/budget_sources.json into draft review state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--catalog",
            default=str(settings.BASE_DIR / "data" / "budget_sources.json"),
            help="Path to the source catalog JSON.",
        )
        parser.add_argument(
            "--jurisdiction",
            action="append",
            dest="jurisdictions",
            help="Limit imports to one or more jurisdiction slugs.",
        )
        parser.add_argument(
            "--include-supporting",
            action="store_true",
            help="Also import records marked verified_supporting.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        catalog_path = Path(options["catalog"]).resolve()
        if not catalog_path.is_file():
            raise CommandError(f"Budget source catalog not found: {catalog_path}")
        try:
            records = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read budget source catalog: {exc}") from exc
        if not isinstance(records, list):
            raise CommandError("Budget source catalog must be a JSON array.")

        allowed_availability = {"verified"}
        if options["include_supporting"]:
            allowed_availability.add("verified_supporting")
        selected_slugs = set(options.get("jurisdictions") or [])
        valid_statuses = {value for value, _label in BudgetDocument.Status.choices}
        selected = []
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict):
                raise CommandError(f"Catalog record {index} must be an object.")
            if record.get("availability") not in allowed_availability:
                continue
            if selected_slugs and record.get("jurisdiction") not in selected_slugs:
                continue
            missing = [name for name in ("jurisdiction", "fiscal_year", "status", "title", "pdf_url") if not record.get(name)]
            if missing:
                raise CommandError(f"Catalog record {index} is missing: {', '.join(missing)}")
            if record["status"] not in valid_statuses:
                raise CommandError(f"Catalog record {index} has invalid status '{record['status']}'.")
            selected.append(record)

        if selected_slugs:
            found = {record["jurisdiction"] for record in selected}
            unavailable = sorted(selected_slugs - found)
            if unavailable:
                self.stdout.write(self.style.WARNING(
                    "No importable verified PDF for: " + ", ".join(unavailable)
                ))
        if not selected:
            self.stdout.write(self.style.WARNING("No verified catalog records matched."))
            return

        failures = []
        for record in selected:
            label = f"{record['jurisdiction']} {record['fiscal_year']} {record['status']}"
            if options["dry_run"]:
                self.stdout.write(f"Would import {label}: {record['pdf_url']}")
                continue
            try:
                call_command(
                    "import_budget_pdf",
                    jurisdiction=record["jurisdiction"],
                    year=int(record["fiscal_year"]),
                    status=record["status"],
                    title=record["title"],
                    url=record["pdf_url"],
                    version_date=record.get("version_date") or None,
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            except Exception as exc:
                failures.append(f"{label}: {exc}")
                self.stderr.write(self.style.ERROR(f"Failed {label}: {exc}"))

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete: {len(selected)} document(s) selected."))
        elif failures:
            raise CommandError(f"Imported catalog with {len(failures)} failure(s).")
        else:
            self.stdout.write(self.style.SUCCESS(f"Catalog import complete: {len(selected)} document(s) processed."))
