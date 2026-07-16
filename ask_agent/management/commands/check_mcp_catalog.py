from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from django.core.management.base import BaseCommand, CommandError

from openskagit_tools.handlers import HANDLERS

Validator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class CatalogCase:
    name: str
    arguments: dict[str, Any]
    validator: Validator


def _require_keys(payload: dict[str, Any], keys: set[str]) -> None:
    missing = sorted(key for key in keys if key not in payload)
    if missing:
        raise ValueError(f"missing keys: {', '.join(missing)}")


def _validate_search(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"query", "count", "results"})


def _validate_parcel(payload: dict[str, Any]) -> None:
    if not (payload.get("parcel_id") or payload.get("parcel")):
        raise ValueError("parcel response has no parcel identifier")


def _validate_overlays(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel", "overlays"})


def _validate_census(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel", "status", "acs"})


def _validate_soils(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel", "status", "mapunits"})


def _validate_layers(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"default_bundles", "bundles", "layers"})
    if not payload["layers"]:
        raise ValueError("layer catalog is empty")


class Command(BaseCommand):
    help = "Run canonical same-process health checks for the unified OpenSkagit tool catalog."

    def add_arguments(self, parser):
        parser.add_argument("--parcel", default="P96023")
        parser.add_argument("--query", default="P96023")
        parser.add_argument("--timeout", type=float, default=60)
        parser.add_argument("--retries", type=int, default=1)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--stop-on-failure", action="store_true")

    def handle(self, *args, **options):
        os.environ["CONTEXT_MCP_TIMEOUT_SECONDS"] = str(options["timeout"])
        os.environ["GIS_MCP_TIMEOUT_SECONDS"] = str(options["timeout"])
        cases = self._cases(str(options["parcel"]).strip().upper(), str(options["query"]).strip())
        results = []
        for case in cases:
            result = self._run_case(case, max(options["retries"], 0), options["json"])
            results.append(result)
            if result["status"] != "ok" and options["stop_on_failure"]:
                break
        if options["json"]:
            self.stdout.write(json.dumps({"endpoint": "canonical-in-process", "results": results}, indent=2))
        failures = [row for row in results if row["status"] != "ok"]
        if failures:
            raise CommandError("Unified catalog check failed for: " + ", ".join(row["tool"] for row in failures))
        self.stdout.write(self.style.SUCCESS(f"All {len(results)} canonical catalog checks passed."))

    def _run_case(self, case: CatalogCase, retries: int, quiet: bool) -> dict[str, Any]:
        failures = []
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                envelope = HANDLERS[case.name](**case.arguments)
                if envelope.get("errors"):
                    raise RuntimeError(str(envelope["errors"]))
                payload = envelope.get("data")
                if not isinstance(payload, dict):
                    raise ValueError("tool data is not an object")
                case.validator(payload)
                result = {
                    "tool": case.name,
                    "status": "ok",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    "summary": self._summarize(payload),
                }
                if not quiet:
                    self.stdout.write(self.style.SUCCESS(f"OK {case.name} ({result['elapsed_ms']} ms): {result['summary']}"))
                return result
            except Exception as exc:
                failures.append({
                    "attempt": attempt + 1,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                if attempt < retries:
                    time.sleep(min(2**attempt, 5))
        result = {"tool": case.name, "status": "failed", "failures": failures}
        if not quiet:
            self.stderr.write(self.style.ERROR(f"FAIL {case.name}: {failures[-1]['error']}"))
        return result

    def _cases(self, parcel: str, query: str) -> list[CatalogCase]:
        return [
            CatalogCase("parcel_search", {"query": query, "limit": 5}, _validate_search),
            CatalogCase("parcel_get_summary", {"parcel_id": parcel}, _validate_parcel),
            CatalogCase("parcel_get_full_report", {"parcel_id": parcel}, _validate_parcel),
            CatalogCase(
                "gis_get_overlays",
                {"parcel_id": parcel, "bundles": "core", "layers": "zoning", "include_parcel_geometry": False},
                _validate_overlays,
            ),
            CatalogCase("context_get_census", {"parcel_id": parcel}, _validate_census),
            CatalogCase("context_get_soils", {"parcel_id": parcel}, _validate_soils),
            CatalogCase("gis_list_layers", {}, _validate_layers),
        ]

    @staticmethod
    def _summarize(payload: dict[str, Any]) -> str:
        parts = []
        if "count" in payload:
            parts.append(f"count={payload['count']}")
        if payload.get("parcel") or payload.get("parcel_id"):
            parts.append(f"parcel={payload.get('parcel') or payload.get('parcel_id')}")
        if "mapunit_count" in payload:
            parts.append(f"mapunits={payload['mapunit_count']}")
        return ", ".join(parts) or "ok"
