"""
run_sfr_baseline_ratio_study -- baseline models + ratio-study report.

Consumes data/processed/sfr_sales_model_dataset.parquet (built by
build_sfr_sales_model_dataset), trains the 4 baseline models on a fixed
80/20 split, computes ratio-study metrics countywide and by group, and
writes data/reports/sfr_baseline_ratio_study.html plus the group/model CSVs.

Baseline only -- no IAAO compliance claim.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from regression import ratio_study, reports_ratio_study
from regression.models import SFRRatioStudyRun

PRB_FORMULA_NOTE = (
    "PRB (Price-Related Bias) follows the IAAO Standard on Ratio Studies (2013): regress "
    "(ratio - median_ratio) / median_ratio on log2[(predicted / median_ratio + actual) / 2]; "
    "the slope is PRB. IAAO's informal acceptable range is roughly [-0.05, 0.05]. This is a "
    "baseline implementation for a prototype, not an IAAO-compliance claim."
)

TEMPORAL_LEAKAGE_WARNING = (
    "This prototype uses current parcel characteristics joined to historical sales. "
    "It may contain temporal leakage where a property changed after the sale date. "
    "Future versions should reconstruct sale-date characteristics or exclude sales "
    "with known post-sale physical changes."
)

DEFAULT_RECENT_YEARS = 5

NEXT_ITERATION_NOTES = [
    "Reconstruct sale-date characteristics (or exclude sales with known post-sale permits/renovations) to remove temporal leakage.",
    "Add time-based and spatial validation splits instead of a single random 80/20 split.",
    "Revisit the 112/113 (secondary detached unit) and 190 (vacation/cabin) exclusions once volume is trusted -- they may be usable with a unit-count feature.",
    "The linear/ridge regressions use a small, simple feature set and no Duan smearing correction on the log back-transform -- both are reasonable next improvements.",
    "Build the automated experiment loop and AI-generated market areas only after this baseline is trusted.",
    "Investigate whether --recent-years should widen once older sales are re-based to sale-date characteristics instead of being excluded outright.",
]


class Command(BaseCommand):
    help = "Train baseline SFR valuation models and produce a ratio-study report. Baseline only, no IAAO compliance claim."

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
            help=(
                "Restrict the ratio study to sales from the most recent N sale years present in the "
                "dataset (default 5). Comparing CURRENT assessed values/model predictions against "
                "SALE PRICES from many decades ago is not a model-quality question -- it is pure "
                "market appreciation. On this data, assessed/sale-price ratios run 40x+ for 1960s "
                "sales, dropping to ~1.0 only in the last few years. Pass 0 to disable and use every "
                "sale (metrics will then be dominated by appreciation, not baseline quality)."
            ),
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        if not input_path.exists():
            raise CommandError(f"{input_path} not found. Run 'python manage.py build_sfr_sales_model_dataset' first.")

        started_at = timezone.now()
        run = SFRRatioStudyRun.objects.create(
            started_at=started_at, status=SFRRatioStudyRun.STATUS_FAILED, recent_years=options["recent_years"]
        )

        try:
            df = pd.read_parquet(input_path)
            total_loaded = len(df)
            self.stdout.write(f"Loaded {total_loaded:,} SFR sales from {input_path}")

            recent_years = options["recent_years"]
            window_note = "all sale years (no recency filter)"
            window_start_year = None
            window_end_year = None
            if recent_years and recent_years > 0:
                window_end_year = int(df["sale_year"].max())
                window_start_year = window_end_year - recent_years + 1
                df = df[df["sale_year"].between(window_start_year, window_end_year)].copy()
                window_note = f"sale years {window_start_year}-{window_end_year} (--recent-years {recent_years})"
                self.stdout.write(
                    f"Restricting to {window_note}: {len(df):,} of {total_loaded:,} sales "
                    "(older sales excluded -- see --help for why)."
                )

            df = ratio_study.prepare_features(df)
            train_df, test_df = ratio_study.split_dataset(df)
            self.stdout.write(f"Train: {len(train_df):,} sales, test: {len(test_df):,} sales (seed={ratio_study.RANDOM_SEED})")

            predictions: dict[str, pd.Series] = {}
            countywide: dict[str, dict] = {}
            for model_name, predict_fn in ratio_study.MODELS.items():
                predicted = predict_fn(train_df, test_df)
                predictions[model_name] = predicted
                countywide[model_name] = ratio_study.compute_ratio_metrics(predicted, test_df["sale_price"])
                self.stdout.write(f"  {model_name}: n={countywide[model_name].get('sale_count', 0):,}")

            # Group reports use the ridge regression model -- the most regularized
            # of the two regressions and the model with the richest feature set.
            primary_model = "ridge_regression"
            primary_predicted = predictions[primary_model]

            group_tables: dict[str, list[dict]] = {}
            for group_col in ratio_study.GROUP_COLUMNS:
                group_df = ratio_study.grouped_ratio_report(test_df, primary_predicted, group_col)
                group_tables[group_col] = group_df.to_dict("records")

            top_misses = {
                model_name: ratio_study.top_prediction_misses(test_df, predicted)
                for model_name, predicted in predictions.items()
            }

            exclusion_summary = self._exclusion_summary()

            self._write_outputs(countywide, group_tables, exclusion_summary, top_misses, primary_model, window_note)
            self._print_summary(countywide, primary_model, window_note)

            model_comparison = [{"model": name, **metrics} for name, metrics in countywide.items()]
            run.finished_at = timezone.now()
            run.status = SFRRatioStudyRun.STATUS_SUCCESS
            run.window_start_year = window_start_year
            run.window_end_year = window_end_year
            run.train_count = len(train_df)
            run.test_count = len(test_df)
            run.primary_model = primary_model
            run.model_comparison = model_comparison
            run.save()
        except Exception as exc:
            run.finished_at = timezone.now()
            run.error = str(exc)[:2000]
            run.save()
            raise

    # ------------------------------------------------------------------
    def _exclusion_summary(self) -> list[dict]:
        try:
            from regression.models import ModelSFRSalesExclusion
            from django.db.models import Count

            rows = (
                ModelSFRSalesExclusion.objects.values("exclusion_reason")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            return [{"value": row["exclusion_reason"], "count": row["count"]} for row in rows]
        except Exception:
            return []

    def _write_outputs(self, countywide, group_tables, exclusion_summary, top_misses, primary_model, window_note) -> None:
        reports_dir = Path(settings.BASE_DIR) / "data" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        model_comparison = [{"model": name, **metrics} for name, metrics in countywide.items()]
        pd.DataFrame(model_comparison).to_csv(reports_dir / "sfr_baseline_model_summary.csv", index=False)

        csv_names = {
            "neighborhood_code": "sfr_baseline_ratio_study_by_neighborhood.csv",
            "city_name": "sfr_baseline_ratio_study_by_city.csv",
            "comp_plan_designation": "sfr_baseline_ratio_study_by_comp_plan.csv",
            "school_district": "sfr_baseline_ratio_study_by_school_district.csv",
            "sale_year": "sfr_baseline_ratio_study_by_sale_year.csv",
            "sale_price_decile": "sfr_baseline_ratio_study_by_price_decile.csv",
        }
        for group_col, filename in csv_names.items():
            pd.DataFrame(group_tables[group_col]).to_csv(reports_dir / filename, index=False)

        html = reports_ratio_study.render_ratio_study_html(
            model_comparison=model_comparison,
            countywide=countywide,
            group_tables=group_tables,
            exclusion_summary=exclusion_summary,
            temporal_leakage_warning=TEMPORAL_LEAKAGE_WARNING,
            prb_formula_note=PRB_FORMULA_NOTE,
            top_misses=top_misses,
            notes=NEXT_ITERATION_NOTES,
            window_note=window_note,
        )
        (reports_dir / "sfr_baseline_ratio_study.html").write_text(html, encoding="utf-8")

    def _print_summary(self, countywide: dict, primary_model: str, window_note: str) -> None:
        out = self.stdout
        out.write("")
        out.write("SFR baseline ratio study complete.")
        out.write(f"Study population: {window_note}")
        out.write("")
        out.write("Model comparison (test set):")
        for model_name, metrics in countywide.items():
            if metrics.get("sale_count", 0) == 0:
                out.write(f"  {model_name}: no usable predictions")
                continue
            out.write(
                f"  {model_name}: n={metrics['sale_count']:,}, median_ratio={metrics['median_ratio']:.3f}, "
                f"COD={metrics['cod']:.1f}, PRD={metrics['prd']:.3f}, PRB={metrics['prb']}, "
                f"median APE={metrics['median_ape']:.1f}%"
            )
        out.write("")
        out.write(f"Group reports computed using: {primary_model}")
        out.write("")
        out.write(self.style.WARNING(f"Temporal leakage warning: {TEMPORAL_LEAKAGE_WARNING}"))
        out.write("")
        out.write(self.style.SUCCESS("Wrote data/reports/sfr_baseline_ratio_study.html"))
        out.write(self.style.SUCCESS("Wrote data/reports/sfr_baseline_model_summary.csv"))
        out.write(self.style.SUCCESS("Wrote 6 group CSVs to data/reports/"))
