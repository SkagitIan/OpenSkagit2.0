from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from opportunity.ai_evals import run_opportunity_ai_evals, write_eval_report


class Command(BaseCommand):
    help = "Run supervised evals for the Opportunity DuckDB/R2 AI search loop."

    def add_arguments(self, parser):
        parser.add_argument("--case", action="append", dest="case_ids", help="Run a single eval case id. Can be repeated.")
        parser.add_argument("--limit", type=int, help="Cap the number of eval cases.")
        parser.add_argument("--cases", help="Path to eval cases JSON. Defaults to data/opportunity_ai_eval_cases.json.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Write machine-readable JSON to stdout.")
        parser.add_argument("--write-report", action="store_true", help="Write a JSON artifact under reports/opportunity_ai_evals.")
        parser.add_argument("--output-dir", help="Directory for --write-report artifacts.")
        parser.add_argument("--repair-report", action="store_true", help="Ask the model for supervised patch proposals for failures.")

    def handle(self, *args, **options):
        _require_live_eval_env()
        try:
            result = run_opportunity_ai_evals(
                cases_path=options.get("cases"),
                case_ids=options.get("case_ids"),
                limit=options.get("limit"),
                repair_report=bool(options.get("repair_report")),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if options.get("write_report"):
            write_eval_report(result, output_dir=options.get("output_dir"))

        payload = result.as_dict()
        if options.get("as_json"):
            self.stdout.write(json.dumps(payload, indent=2, default=str))
        else:
            summary = payload["summary"]
            self.stdout.write(
                f"Opportunity AI evals: {summary['passed']} passed, {summary['failed']} failed, "
                f"{summary['errors']} errors, {summary['total']} total"
            )
            if result.report_path:
                self.stdout.write(f"Report: {Path(result.report_path)}")
            for case in result.cases:
                marker = "OK" if case.status == "passed" else "FAIL"
                self.stdout.write(f"{marker} {case.case.id}: {case.status}")
                for failure in case.failures[:5]:
                    self.stdout.write(f"  - {failure.code}: {failure.message}")
                for action in case.as_dict().get("action_plan", [])[:3]:
                    self.stdout.write(f"  Next: {action}")

        if result.failed_count or result.error_count:
            raise CommandError(f"{result.failed_count} eval(s) failed and {result.error_count} eval(s) errored.")


def _require_live_eval_env() -> None:
    if os.environ.get("OPPORTUNITY_EVALS_LIVE") != "1":
        raise CommandError("Set OPPORTUNITY_EVALS_LIVE=1 to run live Opportunity AI evals.")
    missing = [
        name
        for name in ("OPENAI_API_KEY", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
        if not os.environ.get(name)
    ]
    if missing:
        raise CommandError(f"Missing required env var(s) for live evals: {', '.join(missing)}")
