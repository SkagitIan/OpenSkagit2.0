from __future__ import annotations

import re
from typing import Optional

from agent.catalog.sources import list_sources


COUNT_TERMS = {"count", "counts", "how many", "number of", "total"}


def build_full_catalog_context() -> str:
    """Return the complete catalog of all active sources as a JSON string.

    No scoring, no truncation. Used by the LLM planner so it can reason
    over every available source when forming an evidence plan.
    """
    summaries = [_summarize_source(source) for source in list_sources()]
    return json.dumps({"sources": summaries}, indent=2)


def build_catalog_context(question: str, max_sources: int = 8) -> dict:
    """Return a compact, model-safe catalog subset for planning."""
    summaries = [_summarize_source(source) for source in list_sources()]
    scored = [(_score_summary(question, summary), summary) for summary in summaries]
    relevant = [summary for score, summary in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    if not relevant:
        relevant = summaries[:max_sources]
    return {
        "sources": relevant[:max_sources],
        "query_rules": [
            "Use only source_id values and query_modes listed here.",
            "Do not assume parcel lookup unless the selected source supports parcel entities.",
            "Ask for clarification when a jurisdiction or required entity is missing.",
        ],
    }


def find_catalog_sources(
    domain: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    query_mode: Optional[str] = None,
    count_supported: Optional[bool] = None,
) -> list[dict]:
    summaries = [_summarize_source(source) for source in list_sources()]
    matches = []
    for summary in summaries:
        if domain and domain not in summary["domains"]:
            continue
        if jurisdiction and not _jurisdiction_matches(jurisdiction, summary):
            continue
        if query_mode and query_mode not in summary["query_modes"]:
            continue
        if count_supported is not None and bool(summary.get("count_supported")) != count_supported:
            continue
        matches.append(summary)
    return matches


def get_catalog_source(source_id: str) -> Optional[dict]:
    for source in list_sources():
        if source["id"] == source_id:
            return source
    return None


def summarize_source(source: dict) -> dict:
    return _summarize_source(source)


def source_supports_query(source: dict, query_type: str) -> bool:
    supports = source.get("supports", [])
    return f"query_{query_type}" in supports or query_type in supports


def detect_jurisdiction(question: str, sources: list[dict]) -> Optional[str]:
    for summary in sources:
        for value in summary.get("jurisdiction_aliases", []) + [summary.get("jurisdiction", "")]:
            if value and _contains_phrase(question, value):
                return summary.get("jurisdiction") or value
    return None


def _summarize_source(source: dict) -> dict:
    config = source.get("config") or {}
    capabilities = config.get("capabilities") or {}
    query_modes = capabilities.get("query_modes") or [
        item.removeprefix("query_") for item in source.get("supports", [])
    ]
    jurisdiction = capabilities.get("jurisdiction") or config.get("jurisdiction") or _infer_jurisdiction(source)
    aliases = capabilities.get("jurisdiction_aliases") or config.get("jurisdiction_aliases") or []
    if jurisdiction and jurisdiction not in aliases:
        aliases = [jurisdiction, *aliases]
    return {
        "source_id": source["id"],
        "name": source["name"],
        "jurisdiction": jurisdiction,
        "jurisdiction_aliases": aliases,
        "domains": source.get("domains", []),
        "query_modes": query_modes,
        "entity_types": capabilities.get("entity_types") or _infer_entity_types(query_modes),
        "aggregate_modes": capabilities.get("aggregate_modes", []),
        "count_supported": bool(capabilities.get("count_supported", False)),
        "status_fields": capabilities.get("status_fields", []),
        "usage_notes": capabilities.get("usage_notes") or config.get("note", ""),
    }


def _infer_entity_types(query_modes: list[str]) -> list[str]:
    entity_types = []
    if "by_parcel" in query_modes:
        entity_types.append("parcel")
    if "by_address" in query_modes:
        entity_types.append("address")
    if "by_permit" in query_modes:
        entity_types.append("permit")
    if "by_name" in query_modes or "by_owner" in query_modes:
        entity_types.append("name")
    if "by_date" in query_modes:
        entity_types.append("date_range")
    if not entity_types:
        entity_types.append("geometry")
    return entity_types


def _infer_jurisdiction(source: dict) -> str:
    name = source.get("name", "").lower()
    if "sedro" in name and "woolley" in name:
        return "Sedro-Woolley"
    if "mount vernon" in name:
        return "Mount Vernon"
    if "skagit" in name:
        return "Skagit County"
    if source.get("id", "").startswith("wa_"):
        return "Washington"
    if source.get("id", "").startswith("federal_"):
        return "United States"
    return ""


def _score_summary(question: str, summary: dict) -> int:
    question_lower = question.lower()
    score = 0
    for domain in summary["domains"]:
        if domain.replace("_", " ") in question_lower or domain in question_lower:
            score += 5
    for alias in summary.get("jurisdiction_aliases", []):
        if alias and _contains_phrase(question, alias):
            score += 8
    for token in re.findall(r"[a-z0-9]+", summary["name"].lower()):
        if len(token) > 3 and token in question_lower:
            score += 1
    if "permit" in question_lower and "permits" in summary["domains"]:
        score += 6
    if any(term in question_lower for term in COUNT_TERMS) and summary.get("count_supported"):
        score += 4
    if re.search(r"\bP\d+\b", question, re.IGNORECASE) and "by_parcel" in summary["query_modes"]:
        score += 3
    return score


def _jurisdiction_matches(jurisdiction: str, summary: dict) -> bool:
    return any(_same_text(jurisdiction, value) for value in summary.get("jurisdiction_aliases", []))


def _same_text(left: str, right: str) -> bool:
    return _normalize_text(left) == _normalize_text(right)


def _contains_phrase(text: str, phrase: str) -> bool:
    return _normalize_text(phrase) in _normalize_text(text)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
