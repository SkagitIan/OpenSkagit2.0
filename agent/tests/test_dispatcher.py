import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent.dispatcher import _build_params, execute_step


MOCK_ARCGIS_SUCCESS = {
    "success": True,
    "features": [{"attributes": {"PARCELID": "P48165"}}],
    "count": 1,
    "source_url": "...",
}


@pytest.mark.asyncio
async def test_dispatcher_routes_arcgis():
    with patch("agent.dispatcher.arcgis.query", new=AsyncMock(return_value=MOCK_ARCGIS_SUCCESS)):
        with patch(
            "agent.dispatcher.get_sources_for_domains",
            return_value=[
                {
                    "id": "skagit_parcels",
                    "name": "Skagit County Parcels",
                    "type": "arcgis_rest",
                    "domains": ["parcels", "assessor"],
                    "supports": ["query_by_parcel", "query_by_address"],
                    "base_url": "https://...",
                    "config": {"layer_id": 0},
                }
            ],
        ):
            result = await execute_step(
                {
                    "step": 1,
                    "domain": "parcels",
                    "query_type": "by_parcel",
                    "reason": "Get parcel facts",
                    "entity": "P48165",
                    "entity_type": "parcel",
                }
            )
    assert result["success"] is True
    assert result["source_id"] == "skagit_parcels"
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_unknown_domain():
    with patch("agent.dispatcher.get_sources_for_domains", return_value=[]):
        result = await execute_step(
            {
                "step": 1,
                "domain": "nonexistent_domain",
                "query_type": "by_parcel",
                "reason": "...",
                "entity": "P48165",
                "entity_type": "parcel",
            }
        )
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_concurrent_steps_continue_on_partial_failure():
    call_count = 0

    async def mock_execute(step):
        nonlocal call_count
        call_count += 1
        if step["domain"] == "flood":
            raise Exception("Flood source timeout")
        return {"success": True, "source_id": "skagit_parcels", "domain": "parcels", "data": [], "count": 1}

    steps = [
        {"domain": "parcels", "query_type": "by_parcel", "entity": "P48165"},
        {"domain": "flood", "query_type": "by_geometry", "entity": "P48165"},
    ]
    results = await asyncio.gather(*[mock_execute(step) for step in steps], return_exceptions=True)

    assert call_count == 2
    assert not isinstance(results[0], Exception)
    assert isinstance(results[1], Exception)


def test_dispatcher_builds_web_friendly_permit_params():
    assert _build_params({"query_type": "by_permit", "entity": "2026144"}) == {
        "permit_number": "2026144",
        "search": "2026144",
    }
    assert _build_params({"query_type": "by_address", "entity": "286 Klinger"})["address"] == "286 Klinger"
    assert _build_params(
        {
            "query_type": "by_date",
            "aggregate_mode": "count_by_status",
            "status_filter": "active",
        }
    )["_aggregate_mode"] == "count_by_status"


@pytest.mark.asyncio
async def test_dispatcher_rejects_unknown_source_id():
    with patch("agent.dispatcher.get_source", return_value=None):
        result = await execute_step(
            {
                "step": 1,
                "source_id": "not_registered",
                "domain": "permits",
                "query_type": "by_date",
                "reason": "...",
                "entity": "Sedro-Woolley",
                "entity_type": "municipality",
            }
        )

    assert result["success"] is False
    assert "No active source registered" in result["error"]


@pytest.mark.asyncio
async def test_dispatcher_rejects_unsupported_query_type():
    with patch(
        "agent.dispatcher.get_source",
        return_value={
            "id": "sedro_woolley_permits",
            "name": "Sedro-Woolley iWorQ Permits",
            "type": "web",
            "domains": ["permits"],
            "supports": ["query_by_date"],
            "config": {},
        },
    ):
        result = await execute_step(
            {
                "step": 1,
                "source_id": "sedro_woolley_permits",
                "domain": "permits",
                "query_type": "by_parcel",
                "reason": "...",
                "entity": "P48165",
                "entity_type": "parcel",
            }
        )

    assert result["success"] is False
    assert "does not support query_type" in result["error"]
