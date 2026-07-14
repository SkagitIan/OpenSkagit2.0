"""
Shared execution logic for the per-neighborhood compliance loop -- used by
both the ``run_neighborhood_compliance_loop`` management command (CLI) and
the background-thread runs triggered from the staff dashboard's "Run"
buttons (regression/background.py). Keeping this in one place means the CLI
and the web-triggered runs can never drift apart.

Operates against an already-created ``SFRComplianceLoopRun`` row (status
``running``) and updates it in place with the final status/counts -- the
caller decides how that row got created (CLI creates one per invocation;
the background trigger creates one before starting the thread so the UI has
something to poll immediately).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.utils import timezone

from . import ai_reasoning, reports_compliance_loop, ratio_study, segment_loop
from .models import SFRComplianceLoopRun, SFRSegmentExperiment, SFRSegmentModel

DEFAULT_RECENT_YEARS = 5


def default_input_path() -> Path:
    return Path(settings.BASE_DIR) / "data" / "processed" / "sfr_sales_model_dataset.parquet"


class ComplianceLoopInputMissing(Exception):
    """Raised when the source parquet dataset doesn't exist yet."""


def run_compliance_loop(
    run: SFRComplianceLoopRun,
    input_path: Path | None = None,
    recent_years: int = DEFAULT_RECENT_YEARS,
    segment_scope: str | None = None,
    log=lambda message: None,
) -> None:
    """
    Executes the compliance loop and updates ``run`` in place. ``segment_scope``,
    if given, restricts the run to that one neighborhood_code -- used for the
    per-row "Run just this neighborhood" button. ``log`` is called with each
    progress line (defaults to a no-op for silent background runs; the CLI
    command passes ``self.stdout.write``).
    """
    input_path = input_path or default_input_path()
    if not input_path.exists():
        raise ComplianceLoopInputMissing(f"{input_path} not found. Run 'python manage.py build_sfr_sales_model_dataset' first.")

    try:
        df = pd.read_parquet(input_path)
        total_loaded = len(df)
        log(f"Loaded {total_loaded:,} SFR sales from {input_path}")

        window_note = "all sale years (no recency filter)"
        window_start_year = None
        window_end_year = None
        if recent_years and recent_years > 0:
            window_end_year = int(df["sale_year"].max())
            window_start_year = window_end_year - recent_years + 1
            df = df[df["sale_year"].between(window_start_year, window_end_year)].copy()
            window_note = f"sale years {window_start_year}-{window_end_year} (--recent-years {recent_years})"
            log(f"Restricting to {window_note}: {len(df):,} of {total_loaded:,} sales.")

        df = ratio_study.prepare_features(df)

        if segment_scope:
            neighborhoods = [segment_scope] if segment_scope in set(df["neighborhood_code"].dropna()) else []
            if not neighborhoods:
                raise ValueError(f"Neighborhood code {segment_scope!r} not found in the recent-window dataset.")
        else:
            neighborhoods = sorted(df["neighborhood_code"].dropna().unique())

        log(f"Attempting {len(neighborhoods)} neighborhood(s) (AI model: {ai_reasoning.AI_MODEL}, max {ai_reasoning.MAX_AI_ROUNDS} AI rounds/segment)...")

        segment_results: list[dict] = []
        for neighborhood_code in neighborhoods:
            segment_df = df[df["neighborhood_code"] == neighborhood_code].reset_index(drop=True)
            result = segment_loop.run_segment(neighborhood_code, segment_df)
            segment_results.append(result)
            log(
                f"  {neighborhood_code}: n={result['sample_count']}, status={result['status']}"
                f"{', ai_calls=' + str(result['ai_calls_made']) if result['ai_calls_made'] else ''}"
            )

        _persist_results(segment_results)
        _write_outputs(segment_results, window_note, full_run=not segment_scope)

        counts = {status: sum(1 for r in segment_results if r["status"] == status) for status in ("compliant", "provisional", "dropped")}
        total_ai_calls = sum(r["ai_calls_made"] for r in segment_results)

        log("")
        log("Neighborhood compliance loop complete.")
        log(f"Study population: {window_note}")
        log(f"Compliant: {counts['compliant']}, Provisional: {counts['provisional']}, Dropped: {counts['dropped']}")
        log(f"Total AI-guided calls made: {total_ai_calls}")

        run.finished_at = timezone.now()
        run.status = SFRComplianceLoopRun.STATUS_SUCCESS
        run.recent_years = recent_years
        run.window_start_year = window_start_year
        run.window_end_year = window_end_year
        run.segments_attempted = len(segment_results)
        run.segments_compliant = counts["compliant"]
        run.segments_provisional = counts["provisional"]
        run.segments_dropped = counts["dropped"]
        run.ai_calls_made = total_ai_calls
        run.save()
    except Exception as exc:
        run.finished_at = timezone.now()
        run.status = SFRComplianceLoopRun.STATUS_FAILED
        run.error = str(exc)[:2000]
        run.save()
        raise


def _persist_results(segment_results: list[dict]) -> None:
    processed_segments = [r["segment_value"] for r in segment_results]
    # Scoped delete -- a single-neighborhood run must not wipe every other
    # neighborhood's experiment history, only the segment(s) just re-run.
    SFRSegmentExperiment.objects.filter(segment_value__in=processed_segments).delete()

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


def _write_outputs(segment_results: list[dict], window_note: str, full_run: bool) -> None:
    """
    File exports only make sense for a full county-wide run -- a
    single-neighborhood re-run shouldn't overwrite the countywide JSON/HTML
    with a one-row snapshot.
    """
    if not full_run:
        return

    reports_dir = Path(settings.BASE_DIR) / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    processed_dir = Path(settings.BASE_DIR) / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

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
