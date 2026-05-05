from pathlib import Path

import httpx
import pytest
import respx
import yaml

from agent.adapters.arcgis import query
from agent.adapters.web import _build_form_params, query as web_query


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
    assert source["config"]["capabilities"]["jurisdiction"] == "Sedro-Woolley"
    assert source["config"]["capabilities"]["count_supported"] is True


@respx.mock
@pytest.mark.asyncio
async def test_web_query_sends_aggregate_options():
    route = respx.post("http://localhost:8788/query").mock(
        return_value=httpx.Response(200, json={"success": True, "records": [], "count": 0})
    )
    source = {
        "id": "sedro_woolley_permits",
        "config": {
            "endpoint": "https://sedro-woolley.portal.iworq.net/SEDRO-WOOLLEY/permits/601",
            "method": "GET",
            "query_type": "query_string",
            "response_format": "html_table",
            "search_field_param": "searchField",
            "search_param": "search",
            "permit_date_range_field": "permit_dt_range",
        },
    }

    await web_query(
        source,
        "query_by_date",
        {"_aggregate_mode": "count_by_status", "_status_filter": "active"},
    )

    payload = route.calls.last.request.content
    assert b'"aggregate_mode":"count_by_status"' in payload
    assert b'"status_filter":"active"' in payload
    assert b'"follow_pagination":true' in payload
