import httpx
import pytest
import respx

from agent.adapters.arcgis import query


MOCK_ARCGIS_RESPONSE = {
    "success": True,
    "features": [
        {
            "attributes": {
                "PARCELID": "P48165",
                "OWNER": "TEST OWNER",
                "SITEADDRESS": "123 MAIN ST",
                "ACRES": 1.2,
            }
        }
    ],
    "count": 1,
    "source_url": "https://gis.skagitcounty.net/...",
}


@respx.mock
@pytest.mark.asyncio
async def test_arcgis_query_by_parcel():
    respx.post("http://localhost:8787/query").mock(
        return_value=httpx.Response(200, json=MOCK_ARCGIS_RESPONSE)
    )
    source = {
        "id": "skagit_parcels",
        "base_url": "https://gis.skagitcounty.net/arcgis/rest/services/Parcels/MapServer",
        "config": {"layer_id": 0, "parcel_field": "PARCELID"},
    }
    result = await query(source, "by_parcel", {"parcel_id": "P48165"})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["features"][0]["attributes"]["PARCELID"] == "P48165"


@respx.mock
@pytest.mark.asyncio
async def test_arcgis_query_handles_timeout():
    respx.post("http://localhost:8787/query").mock(side_effect=httpx.TimeoutException("timeout"))
    source = {
        "id": "skagit_parcels",
        "base_url": "https://gis.skagitcounty.net/arcgis/rest/services/Parcels/MapServer",
        "config": {"layer_id": 0},
    }
    result = await query(source, "by_parcel", {"parcel_id": "P48165"})
    assert result["success"] is False
    assert "error" in result
