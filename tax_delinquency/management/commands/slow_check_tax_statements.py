from __future__ import annotations

import os
import time

from django.core.management.base import BaseCommand

from tax_delinquency.models import TaxStatementRun
from tax_delinquency.sync import active_parcel_count, default_years, sync_statements


class Command(BaseCommand):
    help = "Continuously refresh all public tax statements at a slow, configurable cadence."

    def add_arguments(self, parser):
        parser.add_argument("--years", nargs="+", type=int, default=None)
        parser.add_argument("--cycle-hours", type=float, default=float(os.getenv("TAX_DELINQUENCY_CYCLE_HOURS", "168")))
        parser.add_argument("--delay", type=float, default=None)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--stale-hours", type=float, default=None)
        parser.add_argument("--start-after-hours", type=float, default=float(os.getenv("TAX_DELINQUENCY_START_AFTER_HOURS", "0")))
        parser.add_argument("--timeout", type=int, default=int(os.getenv("TAX_DELINQUENCY_TIMEOUT", "20")))
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        years = options["years"] or default_years()
        if options["start_after_hours"]:
            seconds = options["start_after_hours"] * 3600
            self.stdout.write(f"Waiting {options['start_after_hours']} hours before starting slow check.")
            time.sleep(seconds)

        while True:
            parcel_count = options["limit"] if options["limit"] is not None else active_parcel_count()
            statement_count = max(1, parcel_count * len(years))
            delay = options["delay"]
            if delay is None:
                delay = max(0.1, (options["cycle_hours"] * 3600) / statement_count)
            stale_hours = options["stale_hours"] or options["cycle_hours"]

            self.stdout.write(
                f"Starting slow check years={years} parcels={parcel_count} "
                f"cycle_hours={options['cycle_hours']} delay={delay:.2f}s"
            )
            run = sync_statements(
                run_type=TaxStatementRun.RunType.SLOW_CHECK,
                years=years,
                limit=options["limit"],
                delay=delay,
                stale_hours=stale_hours,
                force=False,
                timeout=options["timeout"],
                stdout=self.stdout,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cycle done: attempted={run.statements_attempted} saved={run.statements_saved} "
                    f"skipped={run.statements_skipped} errors={run.errors}"
                )
            )
            if options["once"]:
                break
