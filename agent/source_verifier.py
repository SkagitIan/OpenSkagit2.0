import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from agent.catalog.sources import DB_PATH, list_sources


DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_CONCURRENCY = 8
USER_AGENT = "OpenSkagit source verifier/0.1"
KNOWN_INCOMPLETE_SOURCE_IDS = {"federal_fema_nfhl", "skagit_flood"}
FIELD_ALIASES = {
    "wa_dfw_habitat": {
        "PHS_TYPE": {"PriorityArea_Desc", "PHS_Listing_Desc"},
    }
}


@dataclass
class VerificationResult:
    source_id: str
    source_name: str
    source_type: str
    status: str
    probe_url: str = ""
    http_status: Optional[int] = None
    latency_ms: Optional[int] = None
    detail: str = ""
    error: str = ""
    checked_at: str = ""


async def verify_all_sources(
    *,
    client: Optional[httpx.AsyncClient] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    source_ids: Optional[set[str]] = None,
) -> list[VerificationResult]:
    sources = list_sources()
    if source_ids:
        sources = [source for source in sources if source["id"] in source_ids]

    sem = asyncio.Semaphore(max(1, concurrency))
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True)

    try:
        async def run(source: dict) -> VerificationResult:
            async with sem:
                return await verify_source(client, source)

        return await asyncio.gather(*(run(source) for source in sources))
    finally:
        if own_client:
            await client.aclose()


async def verify_source(client: httpx.AsyncClient, source: dict) -> VerificationResult:
    source_type = source.get("type", "")
    if source_type == "arcgis_rest":
        return await _verify_arcgis(client, source)
    if source_type == "web":
        return await _verify_web(client, source)
    if source_type == "rest_api":
        return await _verify_rest_api(client, source)
    return _result(source, "warning", detail=f"Unsupported source type: {source_type}")


async def _verify_arcgis(client: httpx.AsyncClient, source: dict) -> VerificationResult:
    config = source.get("config") or {}
    base_url = str(source.get("base_url", "")).rstrip("/")
    if not base_url:
        return _result(source, "failed", error="base_url is empty")

    metadata_url = f"{base_url}?f=json"
    started = time.perf_counter()
    try:
        response = await client.get(metadata_url, headers=_headers())
        latency_ms = _elapsed_ms(started)
        data = _json_response(response)
        if response.status_code >= 500:
            return _result(source, "warning", metadata_url, response.status_code, latency_ms, error=f"HTTP {response.status_code}")
        if response.status_code >= 400:
            return _result(source, "failed", metadata_url, response.status_code, latency_ms, error=f"HTTP {response.status_code}")
        if isinstance(data, dict) and data.get("error"):
            return _result(source, "failed", metadata_url, response.status_code, latency_ms, error=_arcgis_error(data["error"]))

        layer_id = config.get("layer_id")
        server_type = config.get("server_type")
        if server_type == "ImageServer":
            return _result(source, "ok", metadata_url, response.status_code, latency_ms, detail="ImageServer metadata OK")
        if not isinstance(layer_id, int):
            return _result(source, "warning", metadata_url, response.status_code, latency_ms, detail="Service metadata OK; no integer layer_id configured")

        layer_url = f"{base_url}/{layer_id}?f=json"
        layer_started = time.perf_counter()
        layer_response = await client.get(layer_url, headers=_headers())
        layer_latency = _elapsed_ms(layer_started)
        layer_data = _json_response(layer_response)
        if layer_response.status_code >= 500:
            return _result(source, "warning", layer_url, layer_response.status_code, layer_latency, error=f"HTTP {layer_response.status_code}")
        if layer_response.status_code >= 400:
            return _result(source, "failed", layer_url, layer_response.status_code, layer_latency, error=f"HTTP {layer_response.status_code}")
        if isinstance(layer_data, dict) and layer_data.get("error"):
            return _result(source, "failed", layer_url, layer_response.status_code, layer_latency, error=_arcgis_error(layer_data["error"]))

        fields = layer_data.get("fields") if isinstance(layer_data, dict) else None
        field_names = {field.get("name") for field in fields or [] if isinstance(field, dict)}
        expected_fields = _configured_fields(config)
        missing_fields = sorted(_missing_configured_fields(source.get("id", ""), expected_fields, field_names)) if field_names else []
        if missing_fields:
            return _result(
                source,
                "failed",
                layer_url,
                layer_response.status_code,
                layer_latency,
                error=f"Configured fields missing: {', '.join(missing_fields)}",
            )

        query_url = f"{base_url}/{layer_id}/query"
        query_started = time.perf_counter()
        query_response = await client.get(
            query_url,
            params={"f": "json", "where": "1=1", "returnCountOnly": "true"},
            headers=_headers(),
        )
        query_latency = _elapsed_ms(query_started)
        query_data = _json_response(query_response)
        if query_response.status_code >= 500:
            return _result(source, "warning", str(query_response.url), query_response.status_code, query_latency, error=f"HTTP {query_response.status_code}")
        if query_response.status_code >= 400:
            return _result(source, "failed", str(query_response.url), query_response.status_code, query_latency, error=f"HTTP {query_response.status_code}")
        if isinstance(query_data, dict) and query_data.get("error"):
            return _result(source, "failed", str(query_response.url), query_response.status_code, query_latency, error=_arcgis_error(query_data["error"]))
        if not isinstance(query_data, dict) or "count" not in query_data:
            return _result(source, "warning", str(query_response.url), query_response.status_code, query_latency, detail="Query OK but count was not returned")
        return _result(source, "ok", str(query_response.url), query_response.status_code, query_latency, detail=f"Layer query OK; count={query_data.get('count')}")
    except Exception as exc:
        return _result(source, "failed", metadata_url, latency_ms=_elapsed_ms(started), error=str(exc))


async def _verify_web(client: httpx.AsyncClient, source: dict) -> VerificationResult:
    config = source.get("config") or {}
    endpoint = str(config.get("endpoint") or source.get("base_url") or "")
    if not endpoint:
        return _result(source, "warning", detail="No endpoint configured")

    method = str(config.get("method") or "GET").upper()
    query_type = str(config.get("query_type") or "query_string")
    params = _web_probe_params(config)
    started = time.perf_counter()
    try:
        if method == "POST" and query_type == "json_post":
            response = await client.post(endpoint, json=params, headers=_headers())
        elif method == "POST":
            response = await client.post(endpoint, data=params, headers={**_headers(), "content-type": "application/x-www-form-urlencoded"})
        else:
            response = await client.get(endpoint, params=params, headers=_headers())
        latency_ms = _elapsed_ms(started)
        if response.status_code >= 500:
            return _result(source, "warning", str(response.url), response.status_code, latency_ms, error=f"HTTP {response.status_code}")
        if response.status_code >= 400:
            return _result(source, "failed", str(response.url), response.status_code, latency_ms, error=f"HTTP {response.status_code}")
        text = response.text[:2000]
        if not text.strip():
            return _result(source, "warning", str(response.url), response.status_code, latency_ms, detail="Endpoint returned an empty body")
        return _result(source, "ok", str(response.url), response.status_code, latency_ms, detail="Web endpoint responded")
    except Exception as exc:
        return _result(source, "failed", endpoint, latency_ms=_elapsed_ms(started), error=str(exc))


async def _verify_rest_api(client: httpx.AsyncClient, source: dict) -> VerificationResult:
    config = source.get("config") or {}
    if config.get("requires_auth"):
        auth_env = _auth_env_name(source, config)
        if not os.environ.get(auth_env):
            return _result(source, "warning", detail=f"Skipped; set {auth_env} to verify authenticated source")

    endpoint = _rest_probe_endpoint(source)
    if not endpoint:
        return _result(source, "warning", detail="No safe probe endpoint configured")

    started = time.perf_counter()
    try:
        response = await client.get(endpoint, headers=_headers())
        latency_ms = _elapsed_ms(started)
        if response.status_code >= 500:
            return _result(source, "warning", str(response.url), response.status_code, latency_ms, error=f"HTTP {response.status_code}")
        if response.status_code >= 400:
            return _result(source, "failed", str(response.url), response.status_code, latency_ms, error=f"HTTP {response.status_code}")
        return _result(source, "ok", str(response.url), response.status_code, latency_ms, detail="REST API endpoint responded")
    except Exception as exc:
        return _result(source, "failed", endpoint, latency_ms=_elapsed_ms(started), error=str(exc))


def save_report(results: list[VerificationResult]) -> dict:
    _ensure_tables()
    run_id = f"svr_{uuid.uuid4().hex[:12]}"
    checked_at = datetime.now(timezone.utc).isoformat()
    summary = summarize(results)
    report = {
        "run_id": run_id,
        "checked_at": checked_at,
        "summary": summary,
        "results": [asdict(result) for result in results],
    }
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO source_verification_runs
              (id, status, checked_at, completed_at, total, ok, warning, failed, duration_ms, report)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                summary["status"],
                checked_at,
                datetime.now(timezone.utc).isoformat(),
                summary["total"],
                summary["ok"],
                summary["warning"],
                summary["failed"],
                summary.get("duration_ms"),
                json.dumps(report),
            ),
        )
        for result in results:
            conn.execute(
                """
                INSERT INTO source_verification_results
                  (id, run_id, source_id, source_name, source_type, status, probe_url, http_status, latency_ms, detail, error, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"svr_result_{uuid.uuid4().hex[:12]}",
                    run_id,
                    result.source_id,
                    result.source_name,
                    result.source_type,
                    result.status,
                    result.probe_url,
                    result.http_status,
                    result.latency_ms,
                    result.detail,
                    result.error,
                    result.checked_at,
                ),
            )
    return report


def summarize(results: list[VerificationResult], duration_ms: Optional[int] = None) -> dict:
    ok = sum(1 for result in results if result.status == "ok")
    warning = sum(1 for result in results if result.status == "warning")
    failed = sum(1 for result in results if result.status == "failed")
    return {
        "status": "failed" if failed else "warning" if warning else "ok",
        "total": len(results),
        "ok": ok,
        "warning": warning,
        "failed": failed,
        "duration_ms": duration_ms,
    }


async def send_alert(report: dict, webhook_url: str) -> None:
    summary = report["summary"]
    failing = [
        result for result in report["results"]
        if result["status"] in {"failed", "warning"}
    ][:20]
    payload = {
        "text": f"OpenSkagit source verification {summary['status']}: {summary['failed']} failed, {summary['warning']} warnings, {summary['ok']} OK",
        "report": {
            "run_id": report["run_id"],
            "checked_at": report["checked_at"],
            "summary": summary,
            "failing": failing,
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(webhook_url, json=payload, headers=_headers())


def print_table(results: list[VerificationResult], summary: dict) -> None:
    print(f"Source verification: {summary['status']} ({summary['ok']} OK, {summary['warning']} warnings, {summary['failed']} failed)")
    print(f"{'source_id':<32} {'status':<8} {'ms':<7} detail")
    print("-" * 96)
    for result in results:
        detail = result.error or result.detail
        latency = "" if result.latency_ms is None else str(result.latency_ms)
        print(f"{result.source_id:<32} {result.status:<8} {latency:<7} {detail[:50]}")


def _ensure_tables() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_verification_runs (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              checked_at TEXT NOT NULL,
              completed_at TEXT,
              total INTEGER NOT NULL,
              ok INTEGER NOT NULL,
              warning INTEGER NOT NULL,
              failed INTEGER NOT NULL,
              duration_ms INTEGER,
              report TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_verification_results (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              source_name TEXT NOT NULL,
              source_type TEXT NOT NULL,
              status TEXT NOT NULL,
              probe_url TEXT,
              http_status INTEGER,
              latency_ms INTEGER,
              detail TEXT,
              error TEXT,
              checked_at TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES source_verification_runs(id)
            );
            """
        )


def _result(
    source: dict,
    status: str,
    probe_url: str = "",
    http_status: Optional[int] = None,
    latency_ms: Optional[int] = None,
    detail: str = "",
    error: str = "",
) -> VerificationResult:
    if status == "failed" and _is_known_incomplete(source):
        status = "warning"
        detail = detail or "Source is marked as needing verification/manual configuration"
    return VerificationResult(
        source_id=source.get("id", ""),
        source_name=source.get("name", ""),
        source_type=source.get("type", ""),
        status=status,
        probe_url=probe_url,
        http_status=http_status,
        latency_ms=latency_ms,
        detail=detail,
        error=error,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def _is_known_incomplete(source: dict) -> bool:
    config = source.get("config") or {}
    status = str(source.get("status") or config.get("status") or "").lower()
    return source.get("id") in KNOWN_INCOMPLETE_SOURCE_IDS or status in {"needs_verification", "needs_manual_config", "pending_verification"}


def _json_response(response: httpx.Response) -> object:
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(f"Response was not JSON: {exc}") from exc


def _headers() -> dict[str, str]:
    return {"user-agent": USER_AGENT, "accept": "application/json,text/html;q=0.8,*/*;q=0.5"}


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _arcgis_error(error: object) -> str:
    if not isinstance(error, dict):
        return str(error)
    message = error.get("message") or "ArcGIS error"
    details = error.get("details")
    if isinstance(details, list) and details:
        return f"{message}: {'; '.join(str(item) for item in details)}"
    return str(message)


def _configured_fields(config: dict) -> set[str]:
    fields = set()
    for key, value in config.items():
        if key.endswith("_field") and isinstance(value, str) and value:
            fields.add(value)
    return fields


def _missing_configured_fields(source_id: str, expected_fields: set[str], field_names: set[str]) -> set[str]:
    missing = set()
    aliases = FIELD_ALIASES.get(source_id, {})
    for field in expected_fields:
        if field in field_names:
            continue
        if aliases.get(field, set()).intersection(field_names):
            continue
        missing.add(field)
    return missing


def _web_probe_params(config: dict) -> dict[str, str]:
    parcel = os.environ.get("SOURCE_VERIFIER_TEST_PARCEL", "P48165")
    params = {}
    parcel_param = config.get("parcel_param")
    if parcel_param:
        params[str(parcel_param)] = parcel
    searchby_param = config.get("searchby_param")
    parcel_searchby_value = config.get("parcel_searchby_value")
    if searchby_param and parcel_searchby_value:
        params[str(searchby_param)] = str(parcel_searchby_value)
    return params


def _rest_probe_endpoint(source: dict) -> str:
    base_url = str(source.get("base_url", "")).rstrip("/")
    if not base_url:
        return ""
    source_id = source.get("id")
    if source_id == "federal_usaspending":
        return f"{base_url}/references/toptier_agencies/"
    return base_url


def _auth_env_name(source: dict, config: dict) -> str:
    if source.get("id") == "federal_sam":
        return "SAM_API_KEY"
    auth_header = str(config.get("auth_header") or "").upper().replace("-", "_")
    return auth_header or "SOURCE_VERIFIER_API_KEY"


def _parse_source_ids(value: str) -> Optional[set[str]]:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


async def async_main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify all configured OpenSkagit sources.")
    parser.add_argument("--concurrency", type=int, default=int(os.environ.get("SOURCE_VERIFIER_CONCURRENCY", DEFAULT_CONCURRENCY)))
    parser.add_argument("--source-ids", default=os.environ.get("SOURCE_VERIFIER_SOURCE_IDS", ""))
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--no-save", action="store_true", help="Do not persist report rows to the SQLite catalog DB.")
    parser.add_argument("--alert-webhook", default=os.environ.get("SOURCE_VERIFIER_ALERT_WEBHOOK", ""))
    parser.add_argument("--alert-on-warning", action="store_true", default=os.environ.get("SOURCE_VERIFIER_ALERT_ON_WARNING", "").lower() in {"1", "true", "yes"})
    args = parser.parse_args(argv)

    started = time.perf_counter()
    results = await verify_all_sources(concurrency=args.concurrency, source_ids=_parse_source_ids(args.source_ids))
    summary = summarize(results, _elapsed_ms(started))
    report = {
        "run_id": "",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "results": [asdict(result) for result in results],
    }
    if not args.no_save:
        report = save_report(results)
        report["summary"]["duration_ms"] = summary["duration_ms"]
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_table(results, summary)

    should_alert = bool(args.alert_webhook) and (summary["failed"] > 0 or (args.alert_on_warning and summary["warning"] > 0))
    if should_alert:
        await send_alert(report, args.alert_webhook)
    return 1 if summary["failed"] else 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
