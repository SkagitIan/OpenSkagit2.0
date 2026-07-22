from __future__ import annotations

import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from budgets.extraction import MAX_PDF_BYTES, extract_pdf
from budgets.models import BudgetDocument, BudgetDocumentPage, BudgetImportRun, BudgetJurisdiction, BudgetLineItem


class Command(BaseCommand):
    help = "Import a budget PDF into draft review state with page text and conservative candidate amounts."

    def add_arguments(self, parser):
        parser.add_argument("--jurisdiction", required=True, help="Jurisdiction slug")
        parser.add_argument("--year", required=True, type=int)
        parser.add_argument("--status", required=True, choices=[value for value, _ in BudgetDocument.Status.choices])
        parser.add_argument("--title", required=True)
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--url")
        source.add_argument("--file")
        parser.add_argument("--source-url", default="", help="Official public URL when importing a local file")
        parser.add_argument("--version-date")

    def handle(self, *args, **options):
        try:
            jurisdiction = BudgetJurisdiction.objects.get(slug=options["jurisdiction"], active=True)
        except BudgetJurisdiction.DoesNotExist as exc:
            raise CommandError("Unknown or inactive budget jurisdiction.") from exc

        try:
            pdf_bytes, source_url, filename = self._read_pdf(options)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Could not retrieve budget PDF: {exc}") from exc
        try:
            digest, pages, candidates, warnings = extract_pdf(pdf_bytes)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        version_date = options.get("version_date") or None
        storage = None
        archived_name = ""
        archive_preexisted = False
        try:
            with transaction.atomic():
                document, created = BudgetDocument.objects.get_or_create(
                    jurisdiction=jurisdiction,
                    source_url=source_url,
                    content_sha256=digest,
                    defaults={
                        "fiscal_year": options["year"],
                        "title": options["title"],
                        "status": options["status"],
                        "version_date": version_date,
                        "retrieved_at": timezone.now(),
                        "published": False,
                    },
                )
                if not created:
                    self.stdout.write(self.style.WARNING(f"Already imported as document {document.pk}."))
                    return

                field = document._meta.get_field("local_file")
                storage = document.local_file.storage
                intended_name = field.generate_filename(document, filename)
                archive_preexisted = storage.exists(intended_name)
                document.local_file.save(filename, ContentFile(pdf_bytes), save=False)
                archived_name = document.local_file.name
                document.page_count = len(pages)
                document.extracted_summary = {
                    "candidate_amount_count": len(candidates),
                    "review_required": True,
                    "warning_count": len(warnings),
                }
                document.save()
                run = BudgetImportRun.objects.create(document=document)
                BudgetDocumentPage.objects.bulk_create(
                    [BudgetDocumentPage(document=document, page_number=page.page_number, text=page.text) for page in pages],
                    batch_size=200,
                )
                BudgetLineItem.objects.bulk_create(
                    [
                        BudgetLineItem(
                            document=document,
                            page_number=row.page_number,
                            fiscal_year=document.fiscal_year,
                            side=BudgetLineItem.Side.OTHER,
                            amount_kind=BudgetLineItem.AmountKind.UNKNOWN,
                            amount=row.amount,
                            raw_label=row.label,
                            raw_data={"raw_line": row.raw_line, "candidate_only": True},
                        )
                        for row in candidates
                    ],
                    batch_size=500,
                )
                run.status = BudgetImportRun.Status.SUCCEEDED
                run.pages_extracted = len(pages)
                run.candidate_line_items = len(candidates)
                run.warnings = warnings
                run.finished_at = timezone.now()
                run.save()
        except Exception as exc:
            cleanup_error = ""
            if storage is not None and archived_name and not archive_preexisted:
                try:
                    storage.delete(archived_name)
                except Exception as cleanup_exc:
                    cleanup_error = f" Archive cleanup also failed for '{archived_name}': {cleanup_exc}"
            raise CommandError(f"Could not persist imported budget: {exc}.{cleanup_error}") from exc

        self.stdout.write(self.style.SUCCESS(
            f"Imported draft document {document.pk}: {len(pages)} pages, {len(candidates)} candidates."
        ))

    def _read_pdf(self, options):
        if options.get("url"):
            url = options["url"]
            request = urllib.request.Request(url, headers={"User-Agent": "OpenSkagit budget importer/1.0"})
            with urllib.request.urlopen(request, timeout=settings.BUDGET_PDF_DOWNLOAD_TIMEOUT_SECONDS) as response:
                data = response.read(MAX_PDF_BYTES + 1)
            filename = Path(urlparse(url).path).name or "budget.pdf"
            return data, url, filename
        path = Path(options["file"]).resolve()
        if not path.is_file():
            raise CommandError(f"PDF not found: {path}")
        source_url = options.get("source_url")
        if not source_url:
            raise CommandError("--source-url is required with --file so citizens can reach the official source.")
        return path.read_bytes(), source_url, path.name
