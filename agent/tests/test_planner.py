"""Tests for the LLM-driven planner.

The planner no longer contains string-matching fallbacks. Every test mocks
``call_model_with_tools`` and verifies that the planner correctly interprets
the structured tool response and propagates it to the caller.
"""

from unittest.mock import AsyncMock, patch

import pytest

from agent.planner import create_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_response(plan: dict):
    """Simulate a successful call_model_with_tools returning a tool input."""
    return AsyncMock(return_value=(plan, None))


def _no_tool_response():
    """Simulate the model returning text instead of a tool call (edge case)."""
    return AsyncMock(return_value=(None, "I cannot determine a plan."))


def _error_response():
    """Simulate the model raising an exception (network failure, quota, etc.)."""
    return AsyncMock(side_effect=RuntimeError("model unavailable"))


# ---------------------------------------------------------------------------
# Parcel question
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parcel_question_basic():
    mock_plan = {
        "entity": "P48165",
        "entity_type": "parcel",
        "steps": [
            {"step": 1, "source_id": "skagit_parcels", "domain": "parcels",
             "query_type": "by_parcel", "reason": "Get basic parcel facts"},
            {"step": 2, "source_id": "skagit_zoning", "domain": "zoning",
             "query_type": "by_parcel", "reason": "Get zoning designation"},
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Tell me about parcel P48165", {"county": "skagit"})
    assert plan["entity"] == "P48165"
    assert plan["entity_type"] == "parcel"
    assert plan["ambiguous"] is False
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["source_id"] == "skagit_parcels"


# ---------------------------------------------------------------------------
# Permit question — open permits in a jurisdiction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_permits_in_sedro_woolley():
    mock_plan = {
        "entity": "Sedro-Woolley",
        "entity_type": "municipality",
        "steps": [
            {
                "step": 1,
                "source_id": "sedro_woolley_permits",
                "domain": "permits",
                "query_type": "by_date",
                "status_filter": "Open",
                "reason": "List all open permits citywide for Sedro-Woolley",
            }
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Get me open permits in Sedro-Woolley", {})
    assert plan["entity"] == "Sedro-Woolley"
    assert plan["entity_type"] == "municipality"
    assert plan["ambiguous"] is False
    step = plan["steps"][0]
    assert step["source_id"] == "sedro_woolley_permits"
    assert step["domain"] == "permits"
    assert step["query_type"] == "by_date"
    assert step.get("status_filter") == "Open"


# ---------------------------------------------------------------------------
# Permit count question
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_permit_count():
    mock_plan = {
        "entity": "Sedro-Woolley",
        "entity_type": "municipality",
        "steps": [
            {
                "step": 1,
                "source_id": "sedro_woolley_permits",
                "domain": "permits",
                "query_type": "by_date",
                "aggregate_mode": "count_by_status",
                "status_filter": "active",
                "reason": "Count active permits in Sedro-Woolley",
            }
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("How many active permits are in Sedro-Woolley?", {})
    assert plan["ambiguous"] is False
    assert plan["entity"] == "Sedro-Woolley"
    assert plan["entity_type"] == "municipality"
    step = plan["steps"][0]
    assert step["source_id"] == "sedro_woolley_permits"
    assert step["aggregate_mode"] == "count_by_status"
    assert step["status_filter"] == "active"


# ---------------------------------------------------------------------------
# Tax history question
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tax_history_by_parcel():
    mock_plan = {
        "entity": "P48165",
        "entity_type": "parcel",
        "steps": [
            {
                "step": 1,
                "source_id": "skagit_treasurer",
                "domain": "taxes",
                "query_type": "by_parcel",
                "reason": "Retrieve tax payment history for the parcel",
            }
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Give me tax history for parcel P48165", {})
    assert plan["entity"] == "P48165"
    assert plan["ambiguous"] is False
    step = plan["steps"][0]
    assert step["source_id"] == "skagit_treasurer"
    assert step["domain"] == "taxes"
    assert step["query_type"] == "by_parcel"


# ---------------------------------------------------------------------------
# Specific permit number lookup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_permit_number_lookup():
    mock_plan = {
        "entity": "2026144",
        "entity_type": "permit",
        "steps": [
            {
                "step": 1,
                "source_id": "sedro_woolley_permits",
                "domain": "permits",
                "query_type": "by_permit",
                "reason": "Look up the specific Sedro-Woolley permit record",
            }
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Look up Sedro-Woolley permit 2026144", {})
    assert plan["entity"] == "2026144"
    assert plan["entity_type"] == "permit"
    step = plan["steps"][0]
    assert step["source_id"] == "sedro_woolley_permits"
    assert step["query_type"] == "by_permit"


# ---------------------------------------------------------------------------
# Wetland question — geometry dependency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wetland_question_requires_parcel_step_first():
    mock_plan = {
        "entity": "P48165",
        "entity_type": "parcel",
        "steps": [
            {
                "step": 1,
                "source_id": "skagit_parcels",
                "domain": "parcels",
                "query_type": "by_parcel",
                "reason": "Get parcel geometry for spatial wetland query",
            },
            {
                "step": 2,
                "source_id": "wa_ecology_wetlands",
                "domain": "wetlands",
                "query_type": "by_geometry",
                "reason": "Check for mapped wetlands overlapping this parcel",
            },
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Are there wetlands near parcel P48165?", {})
    assert plan["ambiguous"] is False
    domains = [s["domain"] for s in plan["steps"]]
    assert domains[0] == "parcels"
    assert "wetlands" in domains


# ---------------------------------------------------------------------------
# Ambiguous question — no entity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ambiguous_question_no_entity():
    mock_plan = {
        "entity": "unknown",
        "entity_type": "parcel",
        "steps": [],
        "ambiguous": True,
        "clarification_needed": "Which parcel ID or address would you like me to look up?",
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Tell me about the property", {})
    assert plan["ambiguous"] is True
    assert plan["clarification_needed"] is not None
    assert plan["steps"] == []


# ---------------------------------------------------------------------------
# Ambiguous jurisdiction — multiple permit sources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ambiguous_jurisdiction_multiple_permit_sources():
    mock_plan = {
        "entity": "unknown",
        "entity_type": "municipality",
        "steps": [],
        "ambiguous": True,
        "clarification_needed": "Which jurisdiction should I use for active permits?",
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("How many active permits are there?", {})
    assert plan["ambiguous"] is True
    assert "jurisdiction" in plan["clarification_needed"].lower()


# ---------------------------------------------------------------------------
# Model failure — returns safe ambiguous response (no silent wrong answer)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_model_failure_returns_ambiguous():
    with patch("agent.planner.call_model_with_tools", new=_error_response()):
        plan = await create_plan("Tell me about parcel P48165", {})
    # Must never silently return a wrong plan — always ask for clarification
    assert plan["ambiguous"] is True
    assert plan["steps"] == []
    assert plan["clarification_needed"] is not None


@pytest.mark.asyncio
async def test_no_tool_call_returns_ambiguous():
    with patch("agent.planner.call_model_with_tools", new=_no_tool_response()):
        plan = await create_plan("Something unclear", {})
    assert plan["ambiguous"] is True
    assert plan["steps"] == []


# ---------------------------------------------------------------------------
# Step numbering is always set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_numbers_are_normalized():
    mock_plan = {
        "entity": "P12345",
        "entity_type": "parcel",
        "steps": [
            {"source_id": "skagit_parcels", "domain": "parcels",
             "query_type": "by_parcel", "reason": "Get parcel"},
            {"source_id": "skagit_zoning", "domain": "zoning",
             "query_type": "by_parcel", "reason": "Get zoning"},
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    with patch("agent.planner.call_model_with_tools", new=_tool_response(mock_plan)):
        plan = await create_plan("Parcel P12345 info", {})
    for i, step in enumerate(plan["steps"], start=1):
        assert step["step"] == i
