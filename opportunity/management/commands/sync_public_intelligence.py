from django.core.management.base import BaseCommand

from opportunity.public_intelligence import sync_public_intelligence_examples


class Command(BaseCommand):
    help = "Copy approved, completed AI search counts into public-safe homepage snapshots."

    def handle(self, *args, **options):
        count = sync_public_intelligence_examples()
        self.stdout.write(self.style.SUCCESS(f"Synced {count} public intelligence examples."))
