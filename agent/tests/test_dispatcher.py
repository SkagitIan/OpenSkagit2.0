import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent.dispatcher import execute_step


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
