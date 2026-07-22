from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from budgets.models import BudgetDocument
from budgets.review import BudgetReviewError, validate_document_for_publication


class Command(BaseCommand):
    help = "Publish a reviewed budget document and optionally make it the jurisdiction default."

    def add_arguments(self, parser):
        parser.add_argument("--document", required=True, type=int)
        parser.add_argument("--current", action="store_true")

    def handle(self, *args, **options):
        try:
            document = BudgetDocument.objects.select_related("jurisdiction").get(pk=options["document"])
        except BudgetDocument.DoesNotExist as exc:
            raise CommandError("Budget document not found.") from exc
        try:
            validate_document_for_publication(document)
        except BudgetReviewError as exc:
            raise CommandError(str(exc)) from exc
        with transaction.atomic():
            if options["current"]:
                BudgetDocument.objects.filter(jurisdiction=document.jurisdiction).update(is_current=False)
                document.is_current = True
            document.published = True
            document.reviewed_at = timezone.now()
            document.save(update_fields=["published", "reviewed_at", "is_current"])
        self.stdout.write(self.style.SUCCESS(f"Published budget document {document.pk}."))
