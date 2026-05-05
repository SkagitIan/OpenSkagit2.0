import json
import re

from agent.catalog.context import (
    build_catalog_context,
    detect_jurisdiction,
    find_catalog_sources,
)
from agent.model import call_model


PLANNER_SYSTEM = """You are a civic evidence planner. Given a question and a compact
catalog of active civic sources, return a JSON plan listing the evidence needed.

Return ONLY valid JSON. No explanation. No markdown.

Schema:
{
  "entity": "string - the parcel ID, address, or entity extracted from the question",
  "entity_type": "parcel | address | district | person | business | permit | municipality | county",
  "steps": [
    {
      "step": 1,
      "source_id": "string - one of the catalog source_id values",
      "domain": "string - one domain from the selected catalog source",
      "query_type": "string - one query mode from the selected catalog source",
      "reason": "string - why this evidence matters for the question"
    }
  ],
  "ambiguous": false,
  "clarification_needed": null
}

Rules:
- Use only source_id values, domains, and query_modes present in catalog_context.
- Do not assume parcel lookup unless the selected source supports parcel entities.
- If a required jurisdiction or entity is missing, set ambiguous to true and ask a precise clarification.
- For count questions, prefer catalog sources with count_supported and aggregate_modes."""


async def create_plan(question: str, context: dict) -> dict:
    catalog_context = build_catalog_context(question)
    prompt = (
        f"Question: {question}\n"
        f"Context: {json.dumps(context)}\n"
        f"Catalog context: {json.dumps(catalog_context)}"
    )
    try:
        response = await call_model(system=PLANNER_SYSTEM, user=prompt, max_tokens=500)
        plan = json.loads(response)
        return _augment_plan(question, plan, catalog_context)
    except Exception:
        return _augment_plan(question, _fallback_plan(question, context), catalog_context)


def _augment_plan(question: str, plan: dict, catalog_context: dict | None = None) -> dict:
    question_lower = question.lower()
    if plan.get("ambiguous"):
        return plan
    steps = plan.setdefault("steps", [])
    sources = (catalog_context or build_catalog_context(question)).get("sources", [])
    source_by_domain = {}
    for source in sources:
        for domain in source.get("domains", []):
            source_by_domain.setdefault(domain, source)

    for index, step in enumerate(steps, start=1):
        step.setdefault("step", index)
        if not step.get("source_id"):
            source = source_by_domain.get(step.get("domain"))
            if source:
                step["source_id"] = source["source_id"]

    def add(domain: str, reason: str) -> None:
        if any(step.get("domain") == domain for step in steps):
            return
        source = source_by_domain.get(domain)
        if not source:
            return
        steps.append(
            {
                "step": len(steps) + 1,
                "source_id": source["source_id"],
                "domain": domain,
                "query_type": _preferred_query_type(source, "by_parcel"),
                "reason": reason,
            }
        )

    if "wetland" in question_lower or "critical area" in question_lower:
        add("wetlands", "Check WA Ecology mapped wetlands")
    if "water right" in question_lower:
        add("water_rights", "Check WA Ecology water-rights records by location")
    if any(term in question_lower for term in ["federal land", "blm", "usfs", "national forest"]):
        add("federal_land", "Check nearby federal surface management boundaries")
    if any(term in question_lower for term in ["wildlife", "habitat", "fish"]):
        add("wildlife_habitat", "Check WA DFW priority habitat records")
    if any(term in question_lower for term in ["elevation", "topography", "slope"]):
        add("elevation", "Check USGS elevation at the parcel")
    return plan


def _fallback_plan(question: str, context: dict) -> dict:
    match = re.search(r"\bP\d+\b", question, re.IGNORECASE)
    permit_match = re.search(r"\b20\d{5,}\b", question)
    entity = context.get("entity") or (match.group(0).upper() if match else "unknown")
    question_lower = question.lower()
    wants_permits = "permit" in question_lower
    wants_count = any(term in question_lower for term in ["how many", "count", "number of", "total"])
    if wants_permits:
        permit_plan = _fallback_permit_plan(question, context, permit_match, wants_count)
        if permit_plan:
            return permit_plan
    if "permit" in question_lower and permit_match:
        entity = context.get("entity") or permit_match.group(0)
    is_investment = any(word in question_lower for word in ["flip", "investment", "develop", "development"])
    wants_environment = any(
        word in question_lower
        for word in ["wetland", "critical area", "environment", "develop", "development", "feasibility"]
    )
    wants_federal_land = any(word in question_lower for word in ["federal land", "blm", "usfs", "national forest"])
    wants_habitat = any(word in question_lower for word in ["wildlife", "habitat", "fish"])
    wants_elevation = any(word in question_lower for word in ["elevation", "topography", "slope"])
    wants_state_land = any(word in question_lower for word in ["state land", "dnr"])
    if wants_permits and permit_match:
        steps = [
            {
                "step": 1,
                "source_id": _first_source_id("permits"),
                "domain": "permits",
                "query_type": "by_permit",
                "reason": "Find the matching Sedro-Woolley permit record",
            }
        ]
    else:
        steps = [
            {
                "step": 1,
                "source_id": _first_source_id("parcels"),
                "domain": "parcels",
                "query_type": "by_parcel",
                "reason": "Get basic parcel facts",
            },
            {
                "step": 2,
                "source_id": _first_source_id("zoning"),
                "domain": "zoning",
                "query_type": "by_parcel",
                "reason": "Get zoning designation",
            },
        ]
    if wants_permits and not permit_match:
        steps.append(
            {
                "step": len(steps) + 1,
                "source_id": _first_source_id("permits"),
                "domain": "permits",
                "query_type": "by_address" if entity != "unknown" else "by_date",
                "reason": "Check Sedro-Woolley permit records",
            }
        )
    if is_investment:
        steps.extend(
            [
                {
                    "step": 3,
                    "source_id": _first_source_id("taxes"),
                    "domain": "taxes",
                    "query_type": "by_parcel",
                    "reason": "Check tax burden and delinquency risk",
                },
                {
                    "step": 4,
                    "source_id": _first_source_id("recorded_documents"),
                    "domain": "recorded_documents",
                    "query_type": "by_parcel",
                    "reason": "Check recent recorded-document activity",
                },
            ]
        )
    if wants_environment:
        steps.extend(
            [
                {
                    "step": len(steps) + 1,
                    "source_id": _first_source_id("wetlands"),
                    "domain": "wetlands",
                    "query_type": "by_parcel",
                    "reason": "Check WA Ecology mapped wetlands",
                },
                {
                    "step": len(steps) + 2,
                    "source_id": _first_source_id("water_rights"),
                    "domain": "water_rights",
                    "query_type": "by_parcel",
                    "reason": "Check WA Ecology water-rights records by location",
                },
            ]
        )
    if wants_federal_land:
        steps.append(
            {
                "step": len(steps) + 1,
                "source_id": _first_source_id("federal_land"),
                "domain": "federal_land",
                "query_type": "by_parcel",
                "reason": "Check nearby federal surface management boundaries",
            }
        )
    if wants_habitat:
        steps.append(
            {
                "step": len(steps) + 1,
                "source_id": _first_source_id("wildlife_habitat"),
                "domain": "wildlife_habitat",
                "query_type": "by_parcel",
                "reason": "Check WA DFW priority habitat records",
            }
        )
    if wants_elevation:
        steps.append(
            {
                "step": len(steps) + 1,
                "source_id": _first_source_id("elevation"),
                "domain": "elevation",
                "query_type": "by_parcel",
                "reason": "Check USGS elevation at the parcel",
            }
        )
    if wants_state_land:
        steps.append(
            {
                "step": len(steps) + 1,
                "source_id": _first_source_id("land_ownership"),
                "domain": "land_ownership",
                "query_type": "by_parcel",
                "reason": "Check WA DNR land ownership records",
            }
        )
    for step in steps:
        step["entity"] = entity
        step["entity_type"] = "parcel"
    return {
        "entity": entity,
        "entity_type": "parcel",
        "steps": steps,
        "ambiguous": entity == "unknown",
        "clarification_needed": None if entity != "unknown" else "Which parcel ID should I look up?",
    }


def _fallback_permit_plan(question: str, context: dict, permit_match: re.Match | None, wants_count: bool) -> dict | None:
    permit_sources = find_catalog_sources(domain="permits")
    if not permit_sources:
        return None
    jurisdiction = context.get("jurisdiction") or detect_jurisdiction(question, permit_sources)
    if wants_count and not jurisdiction and len(permit_sources) > 1:
        return {
            "entity": "unknown",
            "entity_type": "municipality",
            "steps": [],
            "ambiguous": True,
            "clarification_needed": "Which jurisdiction should I use for active permits?",
        }
    source = _select_source(permit_sources, jurisdiction)
    if not source:
        return {
            "entity": "unknown",
            "entity_type": "municipality",
            "steps": [],
            "ambiguous": True,
            "clarification_needed": "Which jurisdiction should I use for active permits?",
        }
    if wants_count:
        entity = jurisdiction or source.get("jurisdiction") or "permits"
        return {
            "entity": entity,
            "entity_type": "municipality",
            "steps": [
                {
                    "step": 1,
                    "source_id": source["source_id"],
                    "domain": "permits",
                    "query_type": _preferred_query_type(source, "by_date"),
                    "aggregate_mode": "count_by_status",
                    "status_filter": "active",
                    "reason": f"Count active permits from {source['name']}",
                }
            ],
            "ambiguous": False,
            "clarification_needed": None,
        }
    if permit_match:
        return {
            "entity": permit_match.group(0),
            "entity_type": "permit",
            "steps": [
                {
                    "step": 1,
                    "source_id": source["source_id"],
                    "domain": "permits",
                    "query_type": _preferred_query_type(source, "by_permit"),
                    "reason": f"Find the matching permit record from {source['name']}",
                }
            ],
            "ambiguous": False,
            "clarification_needed": None,
        }
    return None


def _select_source(sources: list[dict], jurisdiction: str | None) -> dict | None:
    if jurisdiction:
        normalized = re.sub(r"[^a-z0-9]+", " ", jurisdiction.lower()).strip()
        for source in sources:
            aliases = source.get("jurisdiction_aliases", []) + [source.get("jurisdiction", "")]
            for alias in aliases:
                if re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip() == normalized:
                    return source
    if len(sources) == 1:
        return sources[0]
    return None


def _preferred_query_type(source: dict, preferred: str) -> str:
    query_modes = source.get("query_modes", [])
    if preferred in query_modes:
        return preferred
    return query_modes[0] if query_modes else preferred


def _first_source_id(domain: str) -> str | None:
    sources = find_catalog_sources(domain=domain)
    return sources[0]["source_id"] if sources else None
