from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from budgets.models import BudgetJurisdiction


DEFAULT_DATA = Path(settings.BASE_DIR) / "data" / "jurisdiction_population.json"


class Command(BaseCommand):
    help = "Load per-jurisdiction population figures (with a cited source and vintage) used for per-capita comparisons."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_DATA))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()
        if not path.is_file():
            raise CommandError(f"Population data file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read population data: {exc}") from exc

        source = payload.get("source", "")
        source_url = payload.get("source_url", "")
        source_year = payload.get("source_year")
        rows = payload.get("jurisdictions", [])
        if not source or not source_year or not rows:
            raise CommandError("Population data must include source, source_year, and jurisdictions.")

        updated = 0
        missing = []
        for row in rows:
            slug = row.get("jurisdiction", "")
            population = row.get("population")
            if not slug or not isinstance(population, int) or population < 0:
                raise CommandError(f"Invalid population row: {row!r}")
            if options["dry_run"]:
                self.stdout.write(f"Would set {slug}: population={population} ({source}, {source_year})")
                continue
            count = BudgetJurisdiction.objects.filter(slug=slug).update(
                population=population,
                population_source=source,
                population_source_url=source_url,
                population_source_year=source_year,
            )
            if count:
                updated += 1
            else:
                missing.append(slug)

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run passed for {len(rows)} jurisdiction(s)."))
            return
        if missing:
            self.stdout.write(self.style.WARNING("No jurisdiction row for: " + ", ".join(missing)))
        self.stdout.write(self.style.SUCCESS(f"Loaded population for {updated} jurisdiction(s)."))
