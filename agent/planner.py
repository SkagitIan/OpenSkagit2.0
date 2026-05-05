"""Civic evidence planner.

The planner takes a natural-language question and produces a structured
evidence-gathering plan. It works by sending the *complete* source catalog
to a capable LLM and asking it to call a structured tool — no string matching,
no keyword switches, no scoring-based truncation.

Model selection
---------------
Set the ``PLANNER_MODEL`` environment variable to control which model is used.
Prefix the model name with the provider:

    PLANNER_MODEL=claude-opus-4-20250514          # Anthropic (default)
    PLANNER_MODEL=google/gemini-2.5-pro-preview-05-06   # Google Gemini
    PLANNER_MODEL=openai/gpt-4o                  # OpenAI

All three providers are supported via ``model.call_model_with_tools``.

Fallback
--------
If the model call fails for any reason (network error, API quota, malformed
response) the planner returns an ``ambiguous`` plan asking the user to clarify.
There is intentionally no string-matching fallback — if the LLM cannot plan,
we surface that rather than silently doing the wrong thing.
"""

import json

from agent.catalog.context import build_full_catalog_context
from agent.model import call_model_with_tools


# ---------------------------------------------------------------------------
# Tool definition — the planner is forced to call this
# ---------------------------------------------------------------------------

PLAN_TOOL = {
    "name": "create_evidence_plan",
    "description": (
        "Create a structured, step-by-step plan to gather the evidence needed "
        "to answer the user's civic question. Use only source_id values, domains, "
        "and query_modes that appear in the catalog provided."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": (
                    "The primary entity extracted from the question: a parcel ID "
                    "(e.g. P48165), a street address, a person/business name, a "
                    "permit number, or a jurisdiction name. Use 'unknown' only if "
                    "the question is genuinely ambiguous."
                ),
            },
            "entity_type": {
                "type": "string",
                "enum": [
                    "parcel",
                    "address",
                    "district",
                    "person",
                    "business",
                    "permit",
                    "municipality",
                    "county",
                ],
                "description": "The type of the primary entity.",
            },
            "steps": {
                "type": "array",
                "description": "Ordered list of evidence-gathering steps.",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {
                            "type": "integer",
                            "description": "1-based step number.",
                        },
                        "source_id": {
                            "type": "string",
                            "description": "Exact source_id from the catalog.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Domain to query on this source.",
                        },
                        "query_type": {
                            "type": "string",
                            "description": "Query mode to use (must be listed in the source's query_modes).",
                        },
                        "status_filter": {
                            "type": "string",
                            "description": (
                                "Optional status value to filter by "
                                "(e.g. 'Open', 'Active', 'Issued'). "
                                "Use only values found in the source's status_fields."
                            ),
                        },
                        "aggregate_mode": {
                            "type": "string",
                            "description": (
                                "Optional aggregation mode "
                                "(e.g. 'count_by_status'). "
                                "Use only values found in the source's aggregate_modes."
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why this evidence is needed.",
                        },
                    },
                    "required": ["source_id", "domain", "query_type", "reason"],
                },
            },
            "ambiguous": {
                "type": "boolean",
                "description": (
                    "True if the question cannot be answered without more information. "
                    "When true, steps should be empty and clarification_needed must be set."
                ),
            },
            "clarification_needed": {
                "type": ["string", "null"],
                "description": "A single, precise question to ask the user when ambiguous is true.",
            },
        },
        "required": ["entity", "entity_type", "steps", "ambiguous"],
    },
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PLANNER_SYSTEM = """\
You are a civic intelligence planner for Skagit County, Washington.

Your job is to understand the user's question and create a precise plan to \
gather the evidence needed to answer it. You will be given a complete catalog \
of all available data sources.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — UNDERSTAND INTENT (do not skip)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before selecting sources, reason through:
  • What is the user actually trying to learn?
  • What entity is involved? (parcel ID, address, name, permit number, jurisdiction)
  • What is the entity type?
  • Are there implicit steps? (e.g. a wetland question implicitly needs geometry first)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — SELECT SOURCES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use ONLY source_id values, domains, and query_modes that appear in the \
catalog. Never invent source IDs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUERY TYPE REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
by_parcel    — you have a parcel ID (e.g. P48165)
by_address   — you have a street address
by_geometry  — spatial overlay; REQUIRES a parcel step first to obtain geometry
by_date      — jurisdiction-wide or date-range search
by_permit    — you have a specific permit number
by_name      — searching by owner name or business name
by_owner     — searching by owner name

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEPENDENCY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Spatial overlays (wetlands, flood, zoning, habitat, water rights) need \
parcel geometry. Always add a parcels step first when those domains are needed.
• Do NOT add a parcels step unless geometry or basic parcel data is actually \
needed for the question.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS AND AGGREGATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• When filtering by status ("open", "active", "issued"), set status_filter \
using a value from the source's status_fields.
• When counting ("how many", "count", "number of"), set aggregate_mode \
using a value from the source's aggregate_modes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AMBIGUITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Set ambiguous=true when:
  • No entity can be determined and none is in context
  • The question spans multiple jurisdictions and the catalog has a source \
for each — ask which jurisdiction to use
Ask exactly ONE precise clarifying question.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE INTENT → PLAN MAPPINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"open permits in Sedro-Woolley"
  → entity: "Sedro-Woolley", entity_type: municipality
  → step: sedro_woolley_permits, domain: permits, query_type: by_date,
          status_filter: <check source status_fields>, reason: list open permits citywide

"tax history for parcel P48165"
  → entity: "P48165", entity_type: parcel
  → step: skagit_treasurer, domain: taxes, query_type: by_parcel,
          reason: retrieve tax payment and levy history

"who owns 123 Main St Burlington"
  → entity: "123 Main St Burlington", entity_type: address
  → step: skagit_parcels, domain: parcels, query_type: by_address,
          reason: identify owner from parcel record

"are there wetlands near parcel P48165"
  → entity: "P48165", entity_type: parcel
  → step 1: skagit_parcels, domain: parcels, query_type: by_parcel,
             reason: get parcel geometry for spatial query
  → step 2: wa_ecology_wetlands, domain: wetlands, query_type: by_geometry,
             reason: check for mapped wetlands overlapping this parcel

"how many permits were issued in Sedro-Woolley this year"
  → entity: "Sedro-Woolley", entity_type: municipality
  → step: sedro_woolley_permits, domain: permits, query_type: by_date,
          aggregate_mode: count_by_status, reason: count issued permits year-to-date

"recorded documents on parcel P48165"
  → entity: "P48165", entity_type: parcel
  → step: skagit_auditor, domain: recorded_documents, query_type: by_parcel,
          reason: find deeds, easements, and other recorded instruments

"is XYZ Holdings LLC registered in Washington"
  → entity: "XYZ Holdings LLC", entity_type: business
  → step: wa_sos_business, domain: business, query_type: by_name,
          reason: check WA Secretary of State business registry
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def create_plan(question: str, context: dict) -> dict:
    """Create an evidence-gathering plan for the given question.

    Returns a plan dict with keys: entity, entity_type, steps, ambiguous,
    clarification_needed.
    """
    catalog = build_full_catalog_context()
    user_prompt = (
        f"Question: {question}\n\n"
        f"Prior context (may contain entity, jurisdiction, or session info):\n"
        f"{json.dumps(context)}\n\n"
        f"Available sources (complete catalog — use only these):\n"
        f"{catalog}"
    )

    plan_input, _text = await call_model_with_tools(
        system=PLANNER_SYSTEM,
        user=user_prompt,
        tools=[PLAN_TOOL],
        max_tokens=2000,
    )

    if not plan_input:
        return _cannot_plan()

    plan = dict(plan_input)
    steps = plan.get("steps") or []
    for i, step in enumerate(steps, start=1):
        step.setdefault("step", i)
    plan["steps"] = steps
    return plan


def _cannot_plan() -> dict:
    """Returned when the model fails to produce a usable plan."""
    return {
        "entity": "unknown",
        "entity_type": "parcel",
        "steps": [],
        "ambiguous": True,
        "clarification_needed": (
            "I wasn't able to determine how to answer that question. "
            "Could you provide more detail — for example, a parcel ID, "
            "street address, permit number, or specific location?"
        ),
    }
