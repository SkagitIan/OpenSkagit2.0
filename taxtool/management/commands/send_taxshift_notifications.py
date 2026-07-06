from django.core.management.base import BaseCommand

from taxtool.notifications import send_pending_taxshift


class Command(BaseCommand):
    help = "Send pending TaxShift watchlist notifications via Resend."

    def handle(self, *args, **options):
        sent = send_pending_taxshift(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(f"TaxShift notifications: {sent} sent."))
