from __future__ import annotations

import os

from django.core.management.base import BaseCommand

from tax_delinquency.models import TaxStatementRun
from tax_delinquency.sync import default_years, sync_statements


class Command(BaseCommand):
    help = "Backfill public Skagit County tax statements into the local delinquency cache."

    def add_arguments(self, parser):
        parser.add_argument("--years", nargs="+", type=int, default=None)
        parser.add_argument("--parcel", default=None)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--delay", type=float, default=float(os.getenv("TAX_DELINQUENCY_DELAY", "0.35")))
        parser.add_argument("--stale-hours", type=float, default=None)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--timeout", type=int, default=int(os.getenv("TAX_DELINQUENCY_TIMEOUT", "20")))

    def handle(self, *args, **options):
        years = options["years"] or default_years()
        run = sync_statements(
            run_type=TaxStatementRun.RunType.BACKFILL,
            years=years,
            parcel_number=options["parcel"].strip().upper() if options["parcel"] else None,
            limit=options["limit"],
            offset=options["offset"],
            delay=options["delay"],
            stale_hours=options["stale_hours"],
            force=options["force"],
            timeout=options["timeout"],
            stdout=self.stdout,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: attempted={run.statements_attempted} saved={run.statements_saved} "
                f"skipped={run.statements_skipped} errors={run.errors}"
            )
        )
