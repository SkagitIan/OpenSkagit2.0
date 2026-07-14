"""
run_neighborhood_compliance_loop -- per-neighborhood try-then-drop model loop.

For every neighborhood in the recent-window SFR sales dataset, tries the
mechanical model ladder, then (for segments with enough sample) a bounded
Claude-guided adjustment loop, and finally either exports a passing model's
coefficients or drops the segment with a recorded reason. No segment is ever
merged into a city/countywide fallback -- see regression/segment_loop.py.

Thin CLI wrapper around regression/compliance_runner.py, which is shared
with the background-thread runs triggered from the staff dashboard's "Run"
buttons (see regression/background.py).

Baseline reference-range thresholds only -- no IAAO compliance certification
claim (see regression/compliance.py).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from regression import ai_reasoning, compliance_runner
from regression.models import SFRComplianceLoopRun


class Command(BaseCommand):
    help = "Run the per-neighborhood try-then-drop compliance loop and export winning coefficients. Baseline only, no IAAO compliance claim."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default=str(Path(settings.BASE_DIR) / "data" / "processed" / "sfr_sales_model_dataset.parquet"),
            help="Path to the SFR sales model dataset parquet file.",
        )
        parser.add_argument(
            "--recent-years",
            type=int,
            default=compliance_runner.DEFAULT_RECENT_YEARS,
            help="Restrict to sales from the most recent N sale years present in the dataset (default 5, 0 to disable).",
        )
        parser.add_argument(
            "--neighborhood",
            default=None,
            help="Restrict the run to a single neighborhood_code (skips the countywide JSON/HTML export).",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        segment_scope = options["neighborhood"]

        run = SFRComplianceLoopRun.objects.create(
            started_at=timezone.now(),
            status=SFRComplianceLoopRun.STATUS_RUNNING,
            segment_scope=segment_scope or "",
        )

        try:
            compliance_runner.run_compliance_loop(
                run,
                input_path=input_path,
                recent_years=options["recent_years"],
                segment_scope=segment_scope,
                log=self.stdout.write,
            )
        except compliance_runner.ComplianceLoopInputMissing as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Wrote data/processed/neighborhood_price_models.json" if not segment_scope else "(single-neighborhood run -- countywide export files left untouched)"))
        self.stdout.write(self.style.SUCCESS("Wrote data/reports/neighborhood_compliance_loop_summary.html" if not segment_scope else ""))
