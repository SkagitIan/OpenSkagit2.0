from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from taxtool.evals import (
    ERROR,
    WARNING,
    evaluate_tax_reports,
    render_markdown_report,
    render_text_report,
    results_to_json,
    select_eval_parcels,
    summarize_results,
)


class Command(BaseCommand):
    help = "Evaluate TaxShift parcel-report display data against source-data invariants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--parcel",
            action="append",
            default=[],
            help="Parcel number to evaluate. May be provided multiple times.",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=None,
            help="Number of deterministic active parcels to sample. Defaults to 25 unless explicit/recent parcels are provided.",
        )
        parser.add_argument(
            "--recent",
            type=int,
            default=0,
            help="Also evaluate the N most recently searched/opened parcels from ParcelSearchCache.",
        )
        parser.add_argument(
            "--seed",
            default="taxshift-evals-v1",
            help="Seed string for deterministic database sampling.",
        )
        parser.add_argument(
            "--levy-code",
            default=None,
            help="Restrict sampled parcels to a levy code.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json", "markdown"],
            default="text",
            help="Output format.",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Optional file path for the report output.",
        )
        parser.add_argument(
            "--fail-level",
            choices=[ERROR, WARNING, "none"],
            default=ERROR,
            help="Which finding severity should make the command exit non-zero.",
        )

    def handle(self, *args, **options):
        explicit = options["parcel"]
        sample_size = options["sample_size"]
        if sample_size is None:
            sample_size = 0 if explicit or options["recent"] else 25

        parcel_numbers = select_eval_parcels(
            sample_size=sample_size,
            seed=options["seed"],
            recent=options["recent"],
            explicit=explicit,
            levy_code=options["levy_code"],
        )
        if not parcel_numbers:
            raise CommandError("No parcels selected for evaluation.")

        results = evaluate_tax_reports(parcel_numbers)
        if options["format"] == "json":
            output = results_to_json(results)
        elif options["format"] == "markdown":
            output = render_markdown_report(results)
        else:
            output = render_text_report(results)

        if options["output"]:
            Path(options["output"]).write_text(output, encoding="utf-8")
            self.stdout.write(f"Wrote TaxShift eval report to {options['output']}")
        else:
            self.stdout.write(output)

        summary = summarize_results(results)
        if options["fail_level"] == ERROR and summary["error_count"]:
            raise CommandError(f"TaxShift evals found {summary['error_count']} errors.")
        if options["fail_level"] == WARNING and (summary["error_count"] or summary["warning_count"]):
            raise CommandError(
                f"TaxShift evals found {summary['error_count']} errors and {summary['warning_count']} warnings."
            )
