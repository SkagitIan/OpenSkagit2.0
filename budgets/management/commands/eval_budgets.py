from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from budgets import services
from budgets.agent import answer_budget_question


DEFAULT_EVALS = Path(settings.BASE_DIR) / "data" / "budget_evals_2026.json"
NUMBER_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?(?:\s*(?:million|m))?", re.IGNORECASE)


class Command(BaseCommand):
    help = "Run source-backed deterministic budget accuracy checks and optional live chat checks."

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
            raise CommandError(f"Could not read budget evals: {exc}") from exc

        selected = set(options["case_ids"] or [])
        cases = [
            case for case in payload.get("cases", [])
            if not selected or case.get("id") in selected
        ]
        if options["limit"]:
            cases = cases[: max(1, options["limit"])]
        if not cases:
            raise CommandError("No budget eval cases matched.")

        deterministic = [self._run_case(case) for case in cases]
        chat = []
        if options["live_chat"]:
            chat = [self._run_chat_case(case) for case in cases if case.get("question")]

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

        failures = [row for row in deterministic + chat if not row["passed"]]
        if failures:
            raise CommandError(f"Budget eval failed: {len(failures)} case(s).")

    def _run_case(self, case):
        try:
            case_type = case["type"]
            if case_type == "summary":
                result = services.budget_get_summary(case["jurisdiction"], int(case["year"]))
                actual = result["totals"].get(case["side"])
                citation_pages = {
                    item["page"] for item in result["citations"] if item["side"] == case["side"]
                }
                passed = self._close(actual, case["expected"], case.get("tolerance", 0))
                passed = passed and int(case["page"]) in citation_pages
                detail = f"actual={actual}, page={sorted(citation_pages)}"
            elif case_type == "breakdown":
                result = services.budget_get_breakdown(
                    case["jurisdiction"],
                    int(case["year"]),
                    case["side"],
                    case.get("group_by", "auto"),
                    100,
                )
                row = next(
                    (
                        item for item in result["rows"]
                        if item["name"].casefold() == case["name"].casefold()
                    ),
                    None,
                )
                actual = row["amount"] if row else None
                pages = row["pages"] if row else []
                passed = row is not None and self._close(
                    actual, case["expected"], case.get("tolerance", 0)
                )
                passed = passed and int(case["page"]) in pages
                detail = f"actual={actual}, page={pages}"
            elif case_type == "unavailable":
                try:
                    services.budget_get_summary(case["jurisdiction"], int(case["year"]))
                except ValueError as exc:
                    passed = "No reviewed, published budget document" in str(exc)
                    detail = str(exc)
                else:
                    passed = False
                    detail = "Unexpectedly returned published data."
            else:
                return {"id": case.get("id", "unknown"), "passed": False, "detail": "Unknown type."}
        except Exception as exc:
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        return {"id": case["id"], "passed": bool(passed), "detail": detail}

    def _run_chat_case(self, case):
        answer = answer_budget_question(
            case["question"], case["jurisdiction"], int(case["year"])
        )
        lowered = answer.casefold()
        if case["type"] == "unavailable":
            passed = any(
                phrase in lowered
                for phrase in ("no reviewed", "not available", "unavailable", "not located")
            )
            detail = "safe unavailability response" if passed else answer[:240]
            return {"id": case["id"], "passed": passed, "detail": detail}

        expected = Decimal(str(case["expected"]))
        tolerance = max(Decimal(str(case.get("tolerance", 0))), abs(expected) * Decimal("0.001"))
        numeric_match = any(abs(value - expected) <= tolerance for value in self._numbers(answer))
        page = int(case["page"])
        page_match = re.search(rf"\b(?:page|p\.?)[\s#:] *{page}\b", answer, re.IGNORECASE) is not None
        try:
            document = services.budget_get_summary(case["jurisdiction"], int(case["year"]))["document"]
            source_match = document["source_url"] in answer
        except ValueError:
            source_match = False
        passed = numeric_match and page_match and source_match
        detail = (
            f"number={numeric_match}, page={page_match}, source={source_match}; "
            + answer[:180].replace("\n", " ")
        )
        return {"id": case["id"], "passed": passed, "detail": detail}

    @staticmethod
    def _numbers(answer):
        values = []
        for match in NUMBER_RE.finditer(answer):
            token = match.group(0).replace("$", "").replace(",", "").strip().lower()
            multiplier = Decimal("1000000") if token.endswith(("million", "m")) else Decimal("1")
            token = re.sub(r"\s*(million|m)$", "", token)
            try:
                values.append(Decimal(token) * multiplier)
            except InvalidOperation:
                continue
        return values

    @staticmethod
    def _close(actual, expected, tolerance):
        if actual is None:
            return False
        return abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal(str(tolerance))

    @staticmethod
    def _summary(rows):
        passed = sum(1 for row in rows if row["passed"])
        return {
            "total": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "score": round(passed / len(rows), 4) if rows else None,
        }
