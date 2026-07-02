"""Public Python entrypoint for ParcelBook AI parcel search."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agents import Runner

from .agents import build_parcel_search_agent
from .output_models import ParcelAgentAnswer, ParcelResult
from .zoning_router import detect_zoning_need

logger = logging.getLogger(__name__)

ZONING_UNAVAILABLE = "Zoning MCP was not available, so zoning/buildability was not checked."


def _fallback_answer(user_query: str, limit: int, reason: str) -> ParcelAgentAnswer:
    from parcelbook.ai.parcel_query_planner import heuristic_plan
    from .duckdb_tools import execute_parcel_sql

    route = detect_zoning_need(user_query)
    if route["mode"] == "zoning_only":
        return ParcelAgentAnswer(
            interpreted_intent=user_query,
            mode="zoning_only",
            zoning_was_used=False,
            general_caveats=[ZONING_UNAVAILABLE, reason],
        )
    plan = heuristic_plan(user_query)
    data = execute_parcel_sql(plan.sql, limit=limit)
    results = []
    for row in data["rows"][:limit]:
        caveats = list(data["caveats"])
        if route["needs_zoning"]:
            caveats.append(ZONING_UNAVAILABLE)
        results.append(ParcelResult(
            parcel_number=str(row.get("parcel_number", "")),
            address=row.get("situs_address"),
            owner_name=row.get("owner_name"),
            parcel_data=row,
            parcel_match_reason="Matched the parcel-data filters and ranking signals inferred from the question.",
            zoning_summary=None,
            zoning_status="not_checked" if route["needs_zoning"] else None,
            caveats=caveats,
        ))
    return ParcelAgentAnswer(
        interpreted_intent=plan.intent,
        mode=route["mode"],
        sql_used=data["sql"],
        zoning_was_used=False,
        row_count=data["row_count"],
        results=results,
        general_caveats=data["caveats"] + ([ZONING_UNAVAILABLE] if route["needs_zoning"] else []) + [reason],
    )


async def _run_agent(user_query: str, limit: int) -> ParcelAgentAnswer:
    prompt = f"User query: {user_query}\nResult limit: {limit}\nDetect zoning need, read the schema guide, run any needed parcel SQL, and return ParcelAgentAnswer."
    result = await Runner.run(build_parcel_search_agent(), prompt)
    output: Any = result.final_output
    return output if isinstance(output, ParcelAgentAnswer) else ParcelAgentAnswer.model_validate(output)


def ask_parcels(user_query: str, limit: int = 25) -> ParcelAgentAnswer:
    route = detect_zoning_need(user_query)
    logger.info("ParcelBook AI query=%r detected_mode=%s", user_query, route["mode"])
    if not os.environ.get("OPENAI_API_KEY"):
        answer = _fallback_answer(user_query, limit, "OPENAI_API_KEY is not configured; used deterministic fallback planner.")
    else:
        try:
            answer = asyncio.run(_run_agent(user_query, limit))
        except Exception as exc:
            logger.warning("ParcelBook agent failed; using fallback planner: %s", exc)
            answer = _fallback_answer(user_query, limit, f"Agent execution failed; used deterministic fallback planner: {exc}")
    logger.info("ParcelBook AI mode=%s sql=%r row_count=%s zoning_used=%s", answer.mode, answer.sql_used, answer.row_count, answer.zoning_was_used)
    return answer
