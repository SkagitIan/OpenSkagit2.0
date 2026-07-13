"""
build_sfr_sales_model_dataset -- the first SFR sales modeling dataset.

Rebuilds, in order:
  1. model_land_summary       (one row per parcel, from `land`)
  2. model_improvement_summary(one row per parcel, from `improvements`)
  3. model_sfr_sales_dataset  (one row per valid SFR sale)
  4. model_sfr_sales_exclusions (every excluded sale, with a reason)

...then exports data/processed/sfr_sales_model_dataset.parquet,
data/processed/sfr_sales_exclusions.parquet, and the dataset summary report
(data/reports/sfr_sales_dataset_summary.{html,md}) plus a classification
diagnostic (data/reports/sfr_classification_diagnostic.md).

Reads only from source tables (sales, land, improvements, skagit_parcels,
assessor_rollup, parcel_geo_static_features, parcel_primary_zoning) -- never
writes to them. This is a prototype using CURRENT parcel/improvement
characteristics joined to HISTORICAL sales; see the temporal leakage warning
in the generated report.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from regression import pipeline, reports
from regression.models import (
    ModelImprovementSummary,
    ModelLandSummary,
    ModelSFRSalesDataset,
    ModelSFRSalesExclusion,
)


class Command(BaseCommand):
    help = "Build the first SFR sales modeling dataset and exclusion diagnostics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute and print the summary without writing to the database, parquet, or report files.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write("Rebuilding model_land_summary and model_improvement_summary ...")
        with connection.cursor() as cursor:
            land_df = pipeline.fetch_land_summary(cursor)
            improvement_df = pipeline.fetch_improvement_summary(cursor)

        if not dry_run:
            self._replace_table(ModelLandSummary, land_df)
            self._replace_table(ModelImprovementSummary, improvement_df)
        self.stdout.write(f"  land summary: {len(land_df):,} parcels")
        self.stdout.write(f"  improvement summary: {len(improvement_df):,} parcels")

        self.stdout.write("Running SFR classification diagnostic ...")
        with connection.cursor() as cursor:
            diagnostic = pipeline.fetch_sfr_classification_diagnostic(cursor)

        self.stdout.write("Joining sales to parcel/land/improvement/geo/zoning data ...")
        with connection.cursor() as cursor:
            joined_df = pipeline.fetch_sales_join(cursor)

        self.stdout.write("Classifying sales ...")
        included_df, excluded_df = pipeline.classify_sales(joined_df)
        dataset_df = pipeline.build_dataset_frame(included_df)
        exclusion_df = pipeline.build_exclusion_frame(excluded_df)

        summary = reports.compute_dataset_summary(joined_df, dataset_df, exclusion_df)

        if not dry_run:
            self._replace_table(ModelSFRSalesDataset, dataset_df)
            self._replace_table(ModelSFRSalesExclusion, exclusion_df)
            self._write_outputs(dataset_df, exclusion_df, summary, diagnostic)

        self._print_summary(summary, dry_run=dry_run)

    # ------------------------------------------------------------------
    def _replace_table(self, model, df) -> None:
        with transaction.atomic():
            model.objects.all().delete()
            objs = [model(**row) for row in pipeline.records(df)]
            model.objects.bulk_create(objs, batch_size=5000)

    def _write_outputs(self, dataset_df, exclusion_df, summary: dict, diagnostic: dict) -> None:
        processed_dir = Path(settings.BASE_DIR) / "data" / "processed"
        reports_dir = Path(settings.BASE_DIR) / "data" / "reports"
        processed_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        dataset_df.to_parquet(processed_dir / "sfr_sales_model_dataset.parquet", index=False)
        exclusion_df.to_parquet(processed_dir / "sfr_sales_exclusions.parquet", index=False)

        (reports_dir / "sfr_sales_dataset_summary.html").write_text(
            reports.render_dataset_summary_html(summary), encoding="utf-8"
        )
        (reports_dir / "sfr_sales_dataset_summary.md").write_text(
            reports.render_dataset_summary_md(summary), encoding="utf-8"
        )
        (reports_dir / "sfr_classification_diagnostic.md").write_text(
            self._render_diagnostic_md(diagnostic), encoding="utf-8"
        )

    def _render_diagnostic_md(self, diagnostic: dict) -> str:
        lines = [
            "# SFR Classification Diagnostic",
            "",
            "Distinct values inspected on real sales/parcel data before hard-coding SFR",
            "inclusion/exclusion rules. See docs/sfr_modeling_dataset_plan.md for the rules",
            "this evidence informed.",
            "",
        ]
        titles = {
            "sale_type": "sales.sale_type (all sales)",
            "deed_type": "sales.deed_type (all sales, top 25)",
            "land_use_on_valid_sales": "skagit_parcels.land_use on VALID SALE + priced sales",
            "proptype_on_valid_sales": "skagit_parcels.proptype on VALID SALE + priced sales",
            "buildingstyle_on_core_sfr": "skagit_parcels.buildingstyle on VALID SALE + priced + land_use 110/111",
            "exemptions_on_core_sfr": "skagit_parcels.exemptions (non-blank) on VALID SALE + priced + land_use 110/111",
        }
        for key, rows in diagnostic.items():
            lines.append(f"## {titles.get(key, key)}")
            lines.append("")
            for row in rows:
                lines.append(f"- `{row['value']}`: {row['count']:,}")
            lines.append("")
        return "\n".join(lines)

    def _print_summary(self, summary: dict, *, dry_run: bool) -> None:
        out = self.stdout
        out.write("")
        out.write("SFR sales dataset build DRY RUN -- nothing written." if dry_run else "SFR sales dataset build complete.")
        out.write("")
        out.write(f"Total sales loaded: {summary['total_sales_loaded']:,}")
        out.write(f"Retained SFR sales: {summary['retained_sfr_sales']:,} ({summary['retained_pct']:.1f}%)")
        out.write("")
        out.write("Excluded by reason:")
        for row in summary["excluded_by_reason"]:
            out.write(f"  {row['value']}: {row['count']:,}")
        out.write("")
        out.write(self.style.WARNING(f"Temporal leakage warning: {summary['temporal_leakage_warning']}"))
        if not dry_run:
            out.write("")
            out.write(self.style.SUCCESS("Wrote data/processed/sfr_sales_model_dataset.parquet"))
            out.write(self.style.SUCCESS("Wrote data/processed/sfr_sales_exclusions.parquet"))
            out.write(self.style.SUCCESS("Wrote data/reports/sfr_sales_dataset_summary.{html,md}"))
            out.write(self.style.SUCCESS("Wrote data/reports/sfr_classification_diagnostic.md"))
