import json
import os
import re
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from agent import analyst, case_file, dispatcher, export, jobs, notifier, planner
from agent.catalog.sources import DB_PATH, get_sources_for_domains


app = FastAPI(title="Civic Intelligence Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

CASE_CACHE: dict[str, dict] = {}


class NotifyConfig(BaseModel):
    email: Optional[str] = None
    webhook: Optional[str] = None
    subject: Optional[str] = None
    on_confidence: Optional[list[str]] = None


class AskRequest(BaseModel):
    question: str
    context: dict = Field(default_factory=dict)
    notify: Optional[NotifyConfig] = None


class EvidenceItem(BaseModel):
    source_id: str
    source_name: str
    data: dict
    retrieved_at: str


class AskResponse(BaseModel):
    job_id: str
    status: str
    question: str
    answer: Optional[str] = None
    confidence: Optional[str] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    sources_queried: list[str] = Field(default_factory=list)
    case_file_id: Optional[str] = None
    error: Optional[str] = None


class JobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[AskResponse] = None
    error: Optional[str] = None


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    notify_config = request.notify.model_dump(exclude_none=True) if request.notify else None
    result = await run_ask(request.question, request.context, notify_config)
    if not jobs.get_job(result["job_id"]):
        jobs.record_job(result["job_id"], result["status"], result, result.get("error"))
    return AskResponse(**result)


@app.get("/job/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    job = jobs.get_job(job_id)
    if not job:
        return JobStatus(job_id=job_id, status="error", result=None)
    result = AskResponse(**job["result"]) if job.get("result") else None
    return JobStatus(job_id=job_id, status=job["status"], result=result, error=job.get("error"))


@app.get("/notify/status/{job_id}")
async def notify_status(job_id: str):
    """
    Placeholder for notification delivery status.
    Returns 404 in Phase 4. Will be implemented in Phase 5.
    """
    return JSONResponse(
        status_code=404,
        content={"detail": "Notification status not yet implemented"},
    )


@app.get("/case/{case_file_id}")
async def get_case_file(case_file_id: str):
    cf = _load_case_file(case_file_id)
    if not cf:
        return {"success": False, "error": "Case file not found"}
    return cf


@app.get("/export/{case_file_id}")
async def export_case_file(case_file_id: str, format: str = "markdown"):
    cf = _load_case_file(case_file_id)
    if not cf:
        return JSONResponse({"success": False, "error": "Case file not found"})
    if format == "json":
        return JSONResponse(json.loads(export.to_json(cf)))
    return PlainTextResponse(
        export.to_markdown(cf),
        media_type="text/markdown",
        headers={"content-disposition": f'attachment; filename="{case_file_id}.md"'},
    )


@app.get("/cases")
async def list_cases(limit: int = 20, offset: int = 0):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with _connect_cases() as conn:
        rows = conn.execute(
            """
            SELECT id, entity, question, confidence, created_at
            FROM case_files
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return {"cases": [dict(row) for row in rows]}


@app.get("/health")
async def health():
    return {"status": "ok"}


async def run_ask(question: str, context: dict, notify_config: Optional[dict] = None) -> dict:
    job_id = jobs.create_job()

    async def ask_task() -> dict:
        plan = await planner.create_plan(question, context)
        if plan.get("ambiguous"):
            return _response(
                job_id,
                question,
                "complete",
                plan.get("clarification_needed"),
                "low",
                [],
                [plan.get("clarification_needed") or "Question is ambiguous"],
                [],
                None,
            )

        evidence, missing = await _collect_evidence(plan)
        cf = case_file.build(question, plan.get("entity"), evidence, missing)
        try:
            answer = await analyst.respond(question, cf)
        except Exception:
            answer = _fallback_answer(cf)

        result = _response(
            job_id,
            question,
            "complete",
            answer,
            cf["confidence"],
            evidence,
            missing,
            cf["sources_queried"],
            cf["id"],
        )
        cf["answer"] = answer
        _save_case_file(job_id, cf)
        if notify_config:
            asyncio.create_task(notifier.dispatch_background(case_file=cf, notify_config=notify_config))
        return result

    try:
        return await jobs.run_job(job_id, ask_task)
    except Exception as exc:
        result = _response(job_id, question, "error", None, "low", [], [], [], None, str(exc))
        return result


async def _collect_evidence(plan: dict) -> tuple[list[dict], list[str]]:
    import asyncio

    evidence: list[dict] = []
    missing: list[str] = []
    zero_feature_is_evidence = {
        "wetlands",
        "critical_areas",
        "water_rights",
        "wildlife_habitat",
        "federal_land",
        "land_ownership",
    }
    entity = _normalize_entity(plan.get("entity"))
    steps = []
    for step in plan.get("steps", []):
        enriched = {**step}
        enriched.setdefault("entity", entity)
        enriched.setdefault("entity_type", plan.get("entity_type", "parcel"))
        steps.append(enriched)

    parcel_geometry = None
    parcel_steps = [step for step in steps if step.get("domain") == "parcels"]
    remaining_steps = [step for step in steps if step.get("domain") != "parcels"]
    ordered_steps: list[dict] = []
    ordered_results: list[object] = []

    if parcel_steps:
        parcel_result = await dispatcher.execute_step(parcel_steps[0])
        ordered_steps.append(parcel_steps[0])
        ordered_results.append(parcel_result)
        if isinstance(parcel_result, dict):
            parcel_geometry = _extract_geometry(parcel_result.get("data", []))
        remaining_steps = parcel_steps[1:] + remaining_steps

    if parcel_geometry:
        remaining_steps = [_with_geometry_if_needed(step, parcel_geometry) for step in remaining_steps]

    tasks = [dispatcher.execute_step(step) for step in remaining_steps]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ordered_steps.extend(remaining_steps)
    ordered_results.extend(results)

    for step, result in zip(ordered_steps, ordered_results):
        if isinstance(result, Exception):
            missing.append(step["domain"])
            continue
        if result.get("success") and result.get("count", 0) > 0:
            records = _normalize_records(result.get("data", []))
            evidence.append(
                {
                    "source_id": result["source_id"],
                    "source_name": result["source_name"],
                    "data": records[0] if records else {},
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        elif result.get("success") and step["domain"] in zero_feature_is_evidence:
            evidence.append(
                {
                    "source_id": result["source_id"],
                    "source_name": result["source_name"],
                    "data": {
                        "query_status": "no_features",
                        "domain": step["domain"],
                        "message": "No mapped features returned for this location.",
                    },
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            missing.append(result.get("domain") or step["domain"])

    return evidence, missing


def _extract_geometry(data: object) -> Optional[dict]:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        geometry = data[0].get("geometry")
        return geometry if isinstance(geometry, dict) else None
    return None


def _with_geometry_if_needed(step: dict, geometry: dict) -> dict:
    if step.get("query_type") != "by_parcel":
        return step
    sources = get_sources_for_domains([step["domain"]])
    if not sources or sources[0].get("config", {}).get("parcel_field"):
        return step
    return {**step, "query_type": "by_geometry", "geometry": geometry}


def _normalize_records(data: object) -> list[dict]:
    if isinstance(data, list):
        records = data
    else:
        records = [data]
    normalized = []
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("attributes"), dict):
            normalized.append(record["attributes"])
        elif isinstance(record, dict):
            normalized.append(record)
    return normalized


def _fallback_answer(cf: dict) -> str:
    if not cf["evidence"]:
        return "The answer is incomplete because no source returned evidence for this question."
    parts = []
    for item in cf["evidence"]:
        attrs = item["data"]
        if attrs.get("query_status") == "no_features":
            parts.append(f"According to {item['source_name']}, no mapped features were returned for this location.")
            continue
        if item.get("source_id") == "skagit_zoning":
            label = attrs.get("ZONING_LABEL") or attrs.get("LUD_ZONING") or attrs.get("ZONING_CODE")
            code = attrs.get("ZONING_CODE")
            facts = []
            if label:
                facts.append(f"zoning {label}")
            if code:
                facts.append(f"code {code}")
            parts.append(f"According to {item['source_name']}, " + ", ".join(facts or ["zoning data was returned"]) + ".")
            continue
        parcel = attrs.get("PARCELID") or attrs.get("ParcelID") or cf.get("entity")
        owner = attrs.get("OwnerName") or attrs.get("OWNER")
        acres = attrs.get("Acres") if item.get("source_id") == "skagit_parcels" else None
        facts = [f"parcel {parcel}" if parcel else "the parcel"]
        if owner:
            facts.append(f"owner {owner}")
        if acres:
            facts.append(f"{acres} acres")
        parts.append(f"According to {item['source_name']}, " + ", ".join(facts) + ".")
    if cf["missing"]:
        parts.append("Evidence gaps: " + "; ".join(cf["missing"]) + ".")
    return " ".join(parts)


def _normalize_entity(entity: object) -> str:
    text = str(entity or "")
    match = re.search(r"\bP\d+\b", text, re.IGNORECASE)
    return match.group(0).upper() if match else text


def _response(
    job_id: str,
    question: str,
    status: str,
    answer: Optional[str],
    confidence: Optional[str],
    evidence: list[dict],
    missing: list[str],
    sources_queried: list[str],
    case_file_id: Optional[str],
    error: Optional[str] = None,
) -> dict:
    return {
        "job_id": job_id,
        "status": status,
        "question": question,
        "answer": answer,
        "confidence": confidence,
        "evidence": evidence,
        "missing": missing,
        "sources_queried": sources_queried,
        "case_file_id": case_file_id,
        "error": error,
    }


def _connect_cases() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_files (
              id TEXT PRIMARY KEY,
              job_id TEXT NOT NULL,
              question TEXT NOT NULL,
              entity TEXT,
              evidence TEXT NOT NULL,
              missing TEXT NOT NULL,
              confidence TEXT NOT NULL,
              answer TEXT,
              sources_queried TEXT NOT NULL,
              created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
    return conn


def _save_case_file(job_id: str, cf: dict) -> None:
    CASE_CACHE[cf["id"]] = cf
    with _connect_cases() as conn:
        conn.execute(
            """
            INSERT INTO case_files
              (id, job_id, question, entity, evidence, missing, confidence, answer, sources_queried, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              answer=excluded.answer,
              evidence=excluded.evidence,
              missing=excluded.missing,
              confidence=excluded.confidence,
              sources_queried=excluded.sources_queried
            """,
            (
                cf["id"],
                job_id,
                cf["question"],
                cf.get("entity"),
                json.dumps(cf.get("evidence", [])),
                json.dumps(cf.get("missing", [])),
                cf.get("confidence", "low"),
                cf.get("answer"),
                json.dumps(cf.get("sources_queried", [])),
                cf.get("created_at"),
            ),
        )


def _load_case_file(case_file_id: str) -> Optional[dict]:
    if case_file_id in CASE_CACHE:
        return CASE_CACHE[case_file_id]
    with _connect_cases() as conn:
        row = conn.execute("SELECT * FROM case_files WHERE id = ?", (case_file_id,)).fetchone()
    if not row:
        return None
    cf = dict(row)
    cf["evidence"] = json.loads(cf.get("evidence") or "[]")
    cf["missing"] = json.loads(cf.get("missing") or "[]")
    cf["sources_queried"] = json.loads(cf.get("sources_queried") or "[]")
    CASE_CACHE[case_file_id] = cf
    return cf
