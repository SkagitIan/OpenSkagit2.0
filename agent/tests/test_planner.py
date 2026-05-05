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
    assert plan["entity_type"] == "permit"
    assert plan["steps"][0]["source_id"] == "sedro_woolley_permits"
    assert plan["steps"][0]["domain"] == "permits"
    assert plan["steps"][0]["query_type"] == "by_permit"


@pytest.mark.asyncio
async def test_fallback_planner_routes_sedro_woolley_active_permit_count():
    with patch("agent.planner.call_model", new=AsyncMock(side_effect=Exception("model unavailable"))):
        plan = await create_plan("How many active permits are in Sedro-Woolley?", {})

    assert plan["ambiguous"] is False
    assert plan["entity"] == "Sedro-Woolley"
    assert plan["entity_type"] == "municipality"
    assert plan["steps"][0]["source_id"] == "sedro_woolley_permits"
    assert plan["steps"][0]["domain"] == "permits"
    assert plan["steps"][0]["query_type"] == "by_date"
    assert plan["steps"][0]["aggregate_mode"] == "count_by_status"
    assert plan["steps"][0]["status_filter"] == "active"


@pytest.mark.asyncio
async def test_fallback_planner_routes_mount_vernon_from_catalog_without_prompt_edits():
    sources = [
        {
            "id": "sedro_woolley_permits",
            "name": "Sedro-Woolley iWorQ Permits",
            "type": "web",
            "domains": ["permits"],
            "supports": ["query_by_date", "query_by_address", "query_by_permit"],
            "config": {
                "capabilities": {
                    "jurisdiction": "Sedro-Woolley",
                    "jurisdiction_aliases": ["Sedro Woolley"],
                    "query_modes": ["by_date", "by_address", "by_permit"],
                    "count_supported": True,
                    "aggregate_modes": ["count_by_status"],
                }
            },
        },
        {
            "id": "mount_vernon_permits",
            "name": "Mount Vernon Permits",
            "type": "web",
            "domains": ["permits"],
            "supports": ["query_by_date", "query_by_address", "query_by_permit"],
            "config": {
                "capabilities": {
                    "jurisdiction": "Mount Vernon",
                    "jurisdiction_aliases": ["City of Mount Vernon"],
                    "query_modes": ["by_date", "by_address", "by_permit"],
                    "count_supported": True,
                    "aggregate_modes": ["count_by_status"],
                }
            },
        },
    ]

    with patch("agent.catalog.context.list_sources", return_value=sources):
        with patch("agent.planner.call_model", new=AsyncMock(side_effect=Exception("model unavailable"))):
            plan = await create_plan("How many active permits are in Mount Vernon?", {})

    assert plan["ambiguous"] is False
    assert plan["entity"] == "Mount Vernon"
    assert plan["steps"][0]["source_id"] == "mount_vernon_permits"
    assert plan["steps"][0]["domain"] == "permits"


@pytest.mark.asyncio
async def test_fallback_planner_asks_for_jurisdiction_when_multiple_permit_sources_match():
    sources = [
        {
            "id": "sedro_woolley_permits",
            "name": "Sedro-Woolley iWorQ Permits",
            "type": "web",
            "domains": ["permits"],
            "supports": ["query_by_date"],
            "config": {"capabilities": {"jurisdiction": "Sedro-Woolley", "query_modes": ["by_date"]}},
        },
        {
            "id": "mount_vernon_permits",
            "name": "Mount Vernon Permits",
            "type": "web",
            "domains": ["permits"],
            "supports": ["query_by_date"],
            "config": {"capabilities": {"jurisdiction": "Mount Vernon", "query_modes": ["by_date"]}},
        },
    ]

    with patch("agent.catalog.context.list_sources", return_value=sources):
        with patch("agent.planner.call_model", new=AsyncMock(side_effect=Exception("model unavailable"))):
            plan = await create_plan("How many active permits are there?", {})

    assert plan["ambiguous"] is True
    assert plan["clarification_needed"] == "Which jurisdiction should I use for active permits?"
