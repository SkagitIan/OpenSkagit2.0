from pathlib import Path

import httpx
import pytest
import respx
import yaml

from agent.adapters.arcgis import query
from agent.adapters.web import _build_form_params


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


def test_web_adapter_builds_sedro_woolley_date_search_params():
    config = {
        "search_field_param": "searchField",
        "search_param": "search",
        "start_date_param": "startDate",
        "end_date_param": "endDate",
        "permit_date_range_field": "permit_dt_range",
    }

    params = _build_form_params(
        config,
        "query_by_date",
        {"start_date": "2026-04-01", "end_date": "2026-04-28"},
    )

    assert params == {
        "searchField": "permit_dt_range",
        "search": "",
        "startDate": "2026-04-01",
        "endDate": "2026-04-28",
    }


def test_web_adapter_builds_sedro_woolley_address_search_params():
    config = {
        "search_field_param": "searchField",
        "search_param": "search",
        "start_date_param": "startDate",
        "end_date_param": "endDate",
        "site_address_field": "text2",
    }

    params = _build_form_params(config, "query_by_address", {"address": "286 Klinger"})

    assert params == {
        "searchField": "text2",
        "search": "286 Klinger",
        "startDate": "",
        "endDate": "",
    }


def test_sedro_woolley_permit_source_seeded():
    seed_path = Path(__file__).resolve().parents[2] / "catalog" / "seeds" / "skagit_web.yaml"
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    source = data["sources"]["sedro_woolley_permits"]

    assert source["type"] == "web"
    assert "permits" in source["domains"]
    assert source["config"]["query_type"] == "query_string"
    assert source["config"]["permit_date_range_field"] == "permit_dt_range"
