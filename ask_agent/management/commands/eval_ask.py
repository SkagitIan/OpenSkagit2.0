from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ask_agent.agent import (
    QueryResult,
    _status_message,
    _tabulate_tool_output,
    is_safe_analysis_sql,
    result_reality_checks,
)


DEFAULT_EVALS = Path(settings.BASE_DIR) / "data" / "ask_evals_2026.json"


class Command(BaseCommand):
    help = (
        "Run the /ask agent's deterministic regression checks (SQL guardrails, tool-output "
        "tabulation, status messages, reality checks) and optional live end-to-end chat checks."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_EVALS))
        parser.add_argument("--case", action="append", dest="case_ids")
        parser.add_argument("--live-chat", action="store_true")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read ask evals: {exc}") from exc

        selected = set(options["case_ids"] or [])
        cases = [
            case for case in payload.get("cases", [])
            if not selected or case.get("id") in selected
        ]
        if options["limit"]:
            cases = cases[: max(1, options["limit"])]
        if not cases:
            raise CommandError("No ask eval cases matched.")

        deterministic = [self._run_case(case) for case in cases if case.get("type") != "live_chat"]
        chat = []
        if options["live_chat"]:
            chat = [self._run_live_chat_case(case) for case in cases if case.get("type") == "live_chat"]

        report = {
            "version": payload.get("version"),
            "deterministic": self._summary(deterministic),
            "chat": self._summary(chat) if chat else None,
            "results": deterministic,
            "chat_results": chat,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            for row in deterministic:
                mark = "PASS" if row["passed"] else "FAIL"
                self.stdout.write(f"{mark} {row['id']}: {row['detail']}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deterministic: {report['deterministic']['passed']}/"
                    f"{report['deterministic']['total']} passed."
                )
            )
            if chat:
                for row in chat:
                    mark = "PASS" if row["passed"] else "FAIL"
                    self.stdout.write(f"CHAT {mark} {row['id']}: {row['detail']}")
                self.stdout.write(
                    f"Live chat: {report['chat']['passed']}/{report['chat']['total']} passed."
                )
            elif not options["live_chat"] and any(case.get("type") == "live_chat" for case in cases):
                self.stdout.write("(skipped live_chat cases; pass --live-chat to run them)")

        failures = [row for row in deterministic + chat if not row["passed"]]
        if failures:
            raise CommandError(f"Ask eval failed: {len(failures)} case(s).")

    def _run_case(self, case):
        try:
            case_type = case["type"]
            if case_type == "sql_guardrail":
                actual = is_safe_analysis_sql(case["sql"])
                passed = actual == case["expected"]
                detail = f"is_safe_analysis_sql={actual}"
            elif case_type == "tabulate":
                result = _tabulate_tool_output(case["data"])
                actual_columns = result.columns if result else None
                actual_row_count = len(result.rows) if result else None
                passed = actual_columns == case["expected_columns"] and actual_row_count == case["expected_row_count"]
                detail = f"columns={actual_columns}, row_count={actual_row_count}"
            elif case_type == "status_message":
                message = _status_message(case["tool"], case.get("arguments", {}))
                if "expected_equals" in case:
                    passed = message == case["expected_equals"]
                else:
                    passed = case["expected_contains"] in message
                detail = message
            elif case_type == "reality_check":
                result = QueryResult(columns=case["columns"], rows=case["rows"])
                checks = result_reality_checks(result)
                joined = " ".join(checks)
                passed = case["expected_contains"] in joined
                detail = joined or "(no warnings)"
            else:
                return {"id": case.get("id", "unknown"), "passed": False, "detail": f"Unknown type {case_type!r}."}
        except Exception as exc:
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        return {"id": case["id"], "passed": bool(passed), "detail": detail}

    def _run_live_chat_case(self, case):
        from ask_agent.agent import answer_question

        try:
            analysis = answer_question(case["question"])
            lowered = analysis.answer.casefold()
            keywords = case.get("expected_keywords", [])
            passed = all(keyword.casefold() in lowered for keyword in keywords)
            detail = analysis.answer[:220].replace("\n", " ")
        except Exception as exc:
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        return {"id": case["id"], "passed": bool(passed), "detail": detail}

    @staticmethod
    def _summary(rows):
        passed = sum(1 for row in rows if row["passed"])
        return {
            "total": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "score": round(passed / len(rows), 4) if rows else None,
        }
