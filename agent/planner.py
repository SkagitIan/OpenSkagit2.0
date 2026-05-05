import json
import re

from agent.catalog.sources import get_sources_for_domains
from agent.model import call_model


PLANNER_SYSTEM = """You are a civic evidence planner. Given a question about a parcel,
address, or civic entity, return a JSON plan listing the evidence needed and which
source domains to query.

Return ONLY valid JSON. No explanation. No markdown.

Schema:
{
  "entity": "string - the parcel ID, address, or entity extracted from the question",
  "entity_type": "parcel | address | district | person | business",
  "steps": [
    {
      "step": 1,
      "domain": "string - one of the available domains",
      "query_type": "by_parcel | by_address | by_geometry | by_owner | by_name",
      "reason": "string - why this evidence matters for the question"
    }
  ],
  "ambiguous": false,
  "clarification_needed": null
}

If the question is ambiguous (no parcel ID, no address, unclear entity),
set ambiguous to true and clarification_needed to a specific question to ask the user.

Available domains: parcels, zoning, flood, assessor, ownership, planning,
taxes, levy, delinquency, recorded_documents, ownership_history,
easements, permits, federal_spending, federal_contractors,
land_ownership, state_land, dnr, forest, forest_practices,
wetlands, critical_areas, ecology, water_rights, water,
roads, access, transportation, wildlife_habitat, fish_wildlife,
topography, elevation, geology, federal_land, blm, usfs,
business, corporations

For investment or development questions, include taxes and recorded_documents steps.
For federal land or spending questions, include federal_spending steps.
For environmental or development feasibility questions, include:
wetlands, critical_areas, and water_rights steps from WA Ecology.

For questions about land near forests or federal land, include:
federal_land steps from BLM or USFS.

For questions about wildlife, habitat, or critical areas, include:
wildlife_habitat from WA DFW.

For topography or elevation questions, include: elevation from USGS.

For state land ownership questions, include: land_ownership from WA DNR.

Prefer state sources (wa_ecology_wetlands) over county sources
(skagit_flood) when the domain overlaps - state sources have broader
geographic coverage.
Multi-source questions should produce 3-6 steps covering distinct domains."""


async def create_plan(question: str, context: dict) -> dict:
    prompt = f"Question: {question}\nContext: {json.dumps(context)}"
    try:
        response = await call_model(system=PLANNER_SYSTEM, user=prompt, max_tokens=500)
        plan = json.loads(response)
        return _augment_plan(question, plan)
    except Exception:
        return _augment_plan(question, _fallback_plan(question, context))


def _augment_plan(question: str, plan: dict) -> dict:
    question_lower = question.lower()
    if plan.get("ambiguous"):
        return plan
    steps = plan.setdefault("steps", [])
    domains = {step.get("domain") for step in steps}

    def add(domain: str, reason: str) -> None:
        if domain in domains:
            return
        steps.append(
            {
                "step": len(steps) + 1,
                "domain": domain,
                "query_type": "by_parcel",
                "reason": reason,
            }
        )
        domains.add(domain)

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
    entity = context.get("entity") or (match.group(0).upper() if match else "unknown")
    question_lower = question.lower()
    is_investment = any(word in question_lower for word in ["flip", "investment", "develop", "development"])
    wants_environment = any(
        word in question_lower
        for word in ["wetland", "critical area", "environment", "develop", "development", "feasibility"]
    )
    wants_federal_land = any(word in question_lower for word in ["federal land", "blm", "usfs", "national forest"])
    wants_habitat = any(word in question_lower for word in ["wildlife", "habitat", "fish"])
    wants_elevation = any(word in question_lower for word in ["elevation", "topography", "slope"])
    wants_state_land = any(word in question_lower for word in ["state land", "dnr"])
    steps = [
        {
            "step": 1,
            "domain": "parcels",
            "query_type": "by_parcel",
            "reason": "Get basic parcel facts",
        },
        {
            "step": 2,
            "domain": "zoning",
            "query_type": "by_parcel",
            "reason": "Get zoning designation",
        },
    ]
    if is_investment:
        steps.extend(
            [
                {
                    "step": 3,
                    "domain": "taxes",
                    "query_type": "by_parcel",
                    "reason": "Check tax burden and delinquency risk",
                },
                {
                    "step": 4,
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
                    "domain": "wetlands",
                    "query_type": "by_parcel",
                    "reason": "Check WA Ecology mapped wetlands",
                },
                {
                    "step": len(steps) + 2,
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
                "domain": "federal_land",
                "query_type": "by_parcel",
                "reason": "Check nearby federal surface management boundaries",
            }
        )
    if wants_habitat:
        steps.append(
            {
                "step": len(steps) + 1,
                "domain": "wildlife_habitat",
                "query_type": "by_parcel",
                "reason": "Check WA DFW priority habitat records",
            }
        )
    if wants_elevation:
        steps.append(
            {
                "step": len(steps) + 1,
                "domain": "elevation",
                "query_type": "by_parcel",
                "reason": "Check USGS elevation at the parcel",
            }
        )
    if wants_state_land:
        steps.append(
            {
                "step": len(steps) + 1,
                "domain": "land_ownership",
                "query_type": "by_parcel",
                "reason": "Check WA DNR land ownership records",
            }
        )
    for step in steps:
        step["entity"] = entity
        step["entity_type"] = "parcel"
    for step in steps:
        get_sources_for_domains([step["domain"]])
    return {
        "entity": entity,
        "entity_type": "parcel",
        "steps": steps,
        "ambiguous": entity == "unknown",
        "clarification_needed": None if entity != "unknown" else "Which parcel ID should I look up?",
    }
