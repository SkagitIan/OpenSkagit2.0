from unittest.mock import AsyncMock, patch

import pytest

from agent.planner import create_plan


MOCK_PLAN_RESPONSE = """{
  "entity": "P48165",
  "entity_type": "parcel",
  "steps": [
    {"step": 1, "domain": "parcels", "query_type": "by_parcel",
     "reason": "Get basic parcel facts"},
    {"step": 2, "domain": "zoning", "query_type": "by_parcel",
     "reason": "Get zoning designation"}
  ],
  "ambiguous": false,
  "clarification_needed": null
}"""


@pytest.mark.asyncio
async def test_planner_parcel_question():
    with patch("agent.planner.call_model", new=AsyncMock(return_value=MOCK_PLAN_RESPONSE)):
        plan = await create_plan("Tell me about parcel P48165", {"county": "skagit"})
    assert plan["entity"] == "P48165"
    assert plan["ambiguous"] is False
    assert len(plan["steps"]) >= 1
    assert plan["steps"][0]["domain"] in ["parcels", "assessor", "zoning", "flood"]


@pytest.mark.asyncio
async def test_planner_handles_malformed_json():
    with patch("agent.planner.call_model", new=AsyncMock(return_value="not json")):
        plan = await create_plan("Tell me about parcel P48165", {})
    assert "steps" in plan
    assert "entity_type" in plan
    assert plan["entity"] == "P48165"


@pytest.mark.asyncio
async def test_fallback_planner_routes_permit_number_questions_to_permits():
    with patch("agent.planner.call_model", new=AsyncMock(side_effect=Exception("model unavailable"))):
        plan = await create_plan("Look up Sedro-Woolley permit 2026144", {})

    assert plan["entity"] == "2026144"
    assert plan["steps"][0]["domain"] == "permits"
    assert plan["steps"][0]["query_type"] == "by_permit"
