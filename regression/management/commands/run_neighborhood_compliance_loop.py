"""
run_neighborhood_compliance_loop -- per-neighborhood try-then-drop model loop.

For every neighborhood in the recent-window SFR sales dataset, tries the
mechanical model ladder, then (for segments with enough sample) a bounded
Claude-guided adjustment loop, and finally either exports a passing model's
coefficients or drops the segment with a recorded reason. No segment is ever
merged into a city/countywide fallback -- see regression/segment_loop.py.

Baseline reference-range thresholds only -- no IAAO compliance certification
claim (see regression/compliance.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from regression import ai_reasoning, reports_compliance_loop, ratio_study, segment_loop
from regression.models import SFRComplianceLoopRun, SFRSegmentExperiment, SFRSegmentModel

DEFAULT_RECENT_YEARS = 5


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
            default=DEFAULT_RECENT_YEARS,
            help="Restrict to sales from the most recent N sale years present in the dataset (default 5, 0 to disable).",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        if not input_path.exists():
            raise CommandError(f"{input_path} not found. Run 'python manage.py build_sfr_sales_model_dataset' first.")

        started_at = timezone.now()
        run = SFRComplianceLoopRun.objects.create(started_at=started_at, status=SFRComplianceLoopRun.STATUS_FAILED)

        try:
            df = pd.read_parquet(input_path)
            total_loaded = len(df)
            self.stdout.write(f"Loaded {total_loaded:,} SFR sales from {input_path}")

            recent_years = options["recent_years"]
            window_note = "all sale years (no recency filter)"
            if recent_years and recent_years > 0:
                window_end_year = int(df["sale_year"].max())
                window_start_year = window_end_year - recent_years + 1
                df = df[df["sale_year"].between(window_start_year, window_end_year)].copy()
                window_note = f"sale years {window_start_year}-{window_end_year} (--recent-years {recent_years})"
                self.stdout.write(f"Restricting to {window_note}: {len(df):,} of {total_loaded:,} sales.")

            df = ratio_study.prepare_features(df)

            segment_results: list[dict] = []
            neighborhoods = sorted(df["neighborhood_code"].dropna().unique())
            self.stdout.write(f"Attempting {len(neighborhoods)} neighborhoods (AI model: {ai_reasoning.AI_MODEL}, max {ai_reasoning.MAX_AI_ROUNDS} AI rounds/segment)...")

            for neighborhood_code in neighborhoods:
                segment_df = df[df["neighborhood_code"] == neighborhood_code].reset_index(drop=True)
                result = segment_loop.run_segment(neighborhood_code, segment_df)
                segment_results.append(result)
                self.stdout.write(
                    f"  {neighborhood_code}: n={result['sample_count']}, status={result['status']}"
                    f"{', ai_calls=' + str(result['ai_calls_made']) if result['ai_calls_made'] else ''}"
                )

            self._persist_results(segment_results)
            self._write_outputs(segment_results, window_note)

            counts = {status: sum(1 for r in segment_results if r["status"] == status) for status in ("compliant", "provisional", "dropped")}
            total_ai_calls = sum(r["ai_calls_made"] for r in segment_results)

            self._print_summary(counts, total_ai_calls, window_note)

            run.finished_at = timezone.now()
            run.status = SFRComplianceLoopRun.STATUS_SUCCESS
            run.segments_attempted = len(segment_results)
            run.segments_compliant = counts["compliant"]
            run.segments_provisional = counts["provisional"]
            run.segments_dropped = counts["dropped"]
            run.ai_calls_made = total_ai_calls
            run.save()
        except Exception as exc:
            run.finished_at = timezone.now()
            run.error = str(exc)[:2000]
            run.save()
            raise

    # ------------------------------------------------------------------
    def _persist_results(self, segment_results: list[dict]) -> None:
        SFRSegmentExperiment.objects.all().delete()

        experiment_objs = []
        for result in segment_results:
            for exp in result["experiments"]:
                experiment_objs.append(
                    SFRSegmentExperiment(
                        segment_value=result["segment_value"],
                        attempt_kind=exp["attempt_kind"],
                        attempt_number=exp["attempt_number"],
                        train_count=exp["train_count"],
                        test_count=exp["test_count"],
                        metrics=exp["metrics"],
                        passed=exp["passed"],
                        coefficients=exp["coefficients"],
                        ai_rationale=exp["ai_rationale"],
                    )
                )
        if experiment_objs:
            SFRSegmentExperiment.objects.bulk_create(experiment_objs, batch_size=2000)

        for result in segment_results:
            SFRSegmentModel.objects.update_or_create(
                segment_value=result["segment_value"],
                defaults={
                    "model_name": result["model_name"],
                    "coefficients": result["coefficients"],
                    "feature_medians": result["feature_medians"],
                    "metrics": result["metrics"],
                    "sample_count": result["sample_count"],
                    "status": result["status"],
                    "recommendation": result["recommendation"],
                    "attempts_made": result["attempts_made"],
                },
            )

    def _write_outputs(self, segment_results: list[dict], window_note: str) -> None:
        reports_dir = Path(settings.BASE_DIR) / "data" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        processed_dir = Path(settings.BASE_DIR) / "data" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        # Coefficients export -- compliant/provisional segments only, no
        # usable model for a dropped segment.
        exportable = [r for r in segment_results if r["status"] in (segment_loop.STATUS_COMPLIANT, segment_loop.STATUS_PROVISIONAL)]
        export_payload = [
            {
                "neighborhood_code": r["segment_value"],
                "status": r["status"],
                "model_name": r["model_name"],
                "sample_count": r["sample_count"],
                "coefficients": r["coefficients"],
                "feature_medians": r["feature_medians"],
                "metrics": r["metrics"],
            }
            for r in exportable
        ]
        (processed_dir / "neighborhood_price_models.json").write_text(json.dumps(export_payload, indent=2, default=str), encoding="utf-8")

        html = reports_compliance_loop.render_compliance_loop_summary_html(segment_results, window_note, ai_reasoning.AI_MODEL)
        (reports_dir / "neighborhood_compliance_loop_summary.html").write_text(html, encoding="utf-8")

    def _print_summary(self, counts: dict, total_ai_calls: int, window_note: str) -> None:
        out = self.stdout
        out.write("")
        out.write("Neighborhood compliance loop complete.")
        out.write(f"Study population: {window_note}")
        out.write(f"Compliant: {counts['compliant']}, Provisional: {counts['provisional']}, Dropped: {counts['dropped']}")
        out.write(f"Total AI-guided calls made: {total_ai_calls}")
        out.write("")
        out.write(self.style.SUCCESS("Wrote data/processed/neighborhood_price_models.json"))
        out.write(self.style.SUCCESS("Wrote data/reports/neighborhood_compliance_loop_summary.html"))
