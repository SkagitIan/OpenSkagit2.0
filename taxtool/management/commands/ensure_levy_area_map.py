from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Ensure the levy_area_map table is populated; rebuild only if empty (or --force)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild even if levy_area_map already has rows.",
        )

    def handle(self, *args, **options):
        if not options["force"] and self._is_populated():
            self.stdout.write(self.style.SUCCESS("levy_area_map is already populated."))
            return
        call_command("rebuild_levy_area_map")

    def _is_populated(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM levy_area_map")
            return cursor.fetchone()[0] > 0
