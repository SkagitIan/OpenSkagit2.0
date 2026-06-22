from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests
from django.core.management.base import BaseCommand, CommandError

from ask_agent.agent import DEFAULT_OPENSKAGIT_MCP_URL, _call_openskagit_mcp_tool


Validator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class McpCatalogCase:
    name: str
    arguments: dict[str, Any]
    validator: Validator


def _require_keys(payload: dict[str, Any], keys: set[str]) -> None:
    missing = sorted(key for key in keys if key not in payload)
    if missing:
        raise ValueError(f"missing keys: {', '.join(missing)}")


def _validate_search(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"query", "count", "results"})
    if not isinstance(payload["results"], list):
        raise ValueError("results is not a list")


def _validate_property_context(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel", "property", "gis"})


def _validate_property_summary(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel"})
    if len(payload) < 2:
        raise ValueError("property summary did not include any summary fields")


def _validate_gis_overlays(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel"})
    if "layers" not in payload and "overlays" not in payload and "results" not in payload:
        raise ValueError("GIS overlay response did not include layers, overlays, or results")


def _validate_census(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel", "census"})


def _validate_soils(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"parcel", "soils"})


def _validate_layer_list(payload: dict[str, Any]) -> None:
    _require_keys(payload, {"default_bundles", "bundles", "layers"})
    if not payload["layers"]:
        raise ValueError("layer catalog is empty")


class Command(BaseCommand):
    help = "Run an end-to-end health check against every OpenSkagit MCP catalog tool."

    def add_arguments(self, parser):
        parser.add_argument(
            "--parcel",
            default="P96023",
            help="Parcel ID used for parcel-specific MCP checks. Default: P96023.",
        )
        parser.add_argument(
            "--query",
            default="P96023",
            help="Address text or parcel number used for search_parcels. Default: P96023.",
        )
        parser.add_argument(
            "--url",
            default=None,
            help="Optional MCP endpoint override. Also accepted through OPENSKAGIT_MCP_URL.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=60,
            help="Per-tool MCP HTTP timeout in seconds. Default: 60.",
        )
        parser.add_argument(
            "--retries",
            type=int,
            default=1,
            help="Number of retries after a failed tool call. Default: 1.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON results.",
        )
        parser.add_argument(
            "--stop-on-failure",
            action="store_true",
            help="Stop after the first failed MCP tool check.",
        )

    def handle(self, *args, **options):
        if options["url"]:
            os.environ["OPENSKAGIT_MCP_URL"] = options["url"]
        os.environ["OPENSKAGIT_MCP_TIMEOUT_SECONDS"] = str(options["timeout"])

        endpoint = options["url"] or DEFAULT_OPENSKAGIT_MCP_URL
        parcel = str(options["parcel"]).strip().upper()
        query = str(options["query"]).strip()
        cases = self._cases(parcel, query)

        results: list[dict[str, Any]] = []
        for case in cases:
            result = self._run_case(case, retries=max(options["retries"], 0), quiet=options["json"])
            results.append(result)
            if result["status"] != "ok" and options["stop_on_failure"]:
                break

        if options["json"]:
            self.stdout.write(json.dumps({"endpoint": endpoint, "parcel": parcel, "query": query, "results": results}, indent=2))

        failures = [result for result in results if result["status"] != "ok"]
        if failures:
            failed_names = ", ".join(result["tool"] for result in failures)
            raise CommandError(f"OpenSkagit MCP catalog check failed for: {failed_names}")

        self.stdout.write(self.style.SUCCESS(f"All {len(results)} OpenSkagit MCP catalog checks passed."))

    def _run_case(self, case: McpCatalogCase, retries: int, quiet: bool) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                payload = _call_openskagit_mcp_tool(case.name, case.arguments)
                case.validator(payload)
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                result = {
                    "tool": case.name,
                    "status": "ok",
                    "elapsed_ms": elapsed_ms,
                    "attempt": attempt + 1,
                    "summary": self._summarize_payload(payload),
                }
                if attempts:
                    result["previous_failures"] = attempts
                if not quiet:
                    retry_text = f" attempt={attempt + 1}" if attempt else ""
                    self.stdout.write(self.style.SUCCESS(f"OK {case.name} ({elapsed_ms} ms{retry_text}): {result['summary']}"))
                return result
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                failure = {
                    "attempt": attempt + 1,
                    "elapsed_ms": elapsed_ms,
                    "error": self._format_error(exc),
                }
                attempts.append(failure)
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 5))

        result = {
            "tool": case.name,
            "status": "failed",
            "elapsed_ms": attempts[-1]["elapsed_ms"],
            "attempt": attempts[-1]["attempt"],
            "error": attempts[-1]["error"],
            "failures": attempts,
        }
        if not quiet:
            self.stderr.write(self.style.ERROR(f"FAIL {case.name} ({result['elapsed_ms']} ms): {result['error']}"))
        return result

    def _cases(self, parcel: str, query: str) -> list[McpCatalogCase]:
        return [
            McpCatalogCase("search_parcels", {"q": query}, _validate_search),
            McpCatalogCase("get_property_summary", {"parcel": parcel, "raw": False}, _validate_property_summary),
            McpCatalogCase(
                "get_gis_overlays",
                {"parcel": parcel, "bundles": "core", "layers": "zoning"},
                _validate_gis_overlays,
            ),
            McpCatalogCase("get_census_context", {"parcel": parcel}, _validate_census),
            McpCatalogCase("get_soils_context", {"parcel": parcel}, _validate_soils),
            McpCatalogCase("list_gis_layers", {}, _validate_layer_list),
            McpCatalogCase(
                "get_property_context",
                {"parcel": parcel, "raw": False, "bundles": "core", "layers": "zoning"},
                _validate_property_context,
            ),
        ]

    def _summarize_payload(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        if "count" in payload:
            parts.append(f"count={payload['count']}")
        if "parcel" in payload:
            parts.append(f"parcel={payload['parcel']}")
        if "layers" in payload and isinstance(payload["layers"], list):
            parts.append(f"layers={len(payload['layers'])}")
        if "bundles" in payload and isinstance(payload["bundles"], dict):
            parts.append(f"bundles={len(payload['bundles'])}")
        if "meta" in payload and isinstance(payload["meta"], dict):
            tokens = payload["meta"].get("estimated_tokens")
            if tokens is not None:
                parts.append(f"estimated_tokens={tokens}")
        return ", ".join(parts) or f"keys={','.join(sorted(payload.keys())[:8])}"

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        return f"{type(exc).__name__}: {exc}"
