import sqlite3

import httpx
import pytest

from agent import source_verifier


@pytest.mark.asyncio
async def test_arcgis_source_verifies_metadata_layer_and_count():
    source = {
        "id": "skagit_parcels",
        "name": "Skagit County Parcels",
        "type": "arcgis_rest",
        "base_url": "https://example.test/arcgis/rest/services/Assessor/PropertyMap/MapServer",
        "config": {"layer_id": 5, "parcel_field": "PARCELID"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/MapServer"):
            return httpx.Response(200, json={"layers": [{"id": 5}]}, request=request)
        if path.endswith("/MapServer/5"):
            return httpx.Response(200, json={"fields": [{"name": "PARCELID"}]}, request=request)
        if path.endswith("/MapServer/5/query"):
            return httpx.Response(200, json={"count": 123}, request=request)
        return httpx.Response(404, json={}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await source_verifier.verify_source(client, source)

    assert result.status == "ok"
    assert result.http_status == 200
    assert "count=123" in result.detail


@pytest.mark.asyncio
async def test_arcgis_source_fails_when_configured_field_is_missing():
    source = {
        "id": "skagit_zoning",
        "name": "Skagit County Zoning",
        "type": "arcgis_rest",
        "base_url": "https://example.test/arcgis/rest/services/Zoning/MapServer",
        "config": {"layer_id": 8, "zone_field": "ZONING_CODE"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/MapServer"):
            return httpx.Response(200, json={"layers": [{"id": 8}]}, request=request)
        if request.url.path.endswith("/MapServer/8"):
            return httpx.Response(200, json={"fields": [{"name": "OTHER_FIELD"}]}, request=request)
        return httpx.Response(200, json={"count": 1}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await source_verifier.verify_source(client, source)

    assert result.status == "failed"
    assert "ZONING_CODE" in result.error


@pytest.mark.asyncio
async def test_web_source_without_endpoint_is_warning():
    source = {
        "id": "skagit_auditor",
        "name": "Skagit County Auditor",
        "type": "web",
        "base_url": "",
        "config": {"endpoint": ""},
    }

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))) as client:
        result = await source_verifier.verify_source(client, source)

    assert result.status == "warning"
    assert "No endpoint" in result.detail


@pytest.mark.asyncio
async def test_known_incomplete_arcgis_failure_is_warning():
    source = {
        "id": "federal_usgs_geology",
        "name": "USGS Geologic Map",
        "type": "arcgis_rest",
        "base_url": "https://example.test/broken/MapServer",
        "config": {"layer_id": 0, "status": "needs_verification"},
    }

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404, json={}, request=request))
    ) as client:
        result = await source_verifier.verify_source(client, source)

    assert result.status == "warning"
    assert result.error == "HTTP 404"


def test_save_report_persists_run_and_results(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setattr(source_verifier, "DB_PATH", str(db_path))
    results = [
        source_verifier.VerificationResult(
            source_id="source_one",
            source_name="Source One",
            source_type="arcgis_rest",
            status="ok",
            detail="OK",
            checked_at="2026-05-05T00:00:00+00:00",
        )
    ]

    report = source_verifier.save_report(results)

    with sqlite3.connect(db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) FROM source_verification_runs").fetchone()[0]
        result_count = conn.execute("SELECT COUNT(*) FROM source_verification_results").fetchone()[0]

    assert report["summary"]["ok"] == 1
    assert run_count == 1
    assert result_count == 1


def test_configured_field_aliases_allow_stale_catalog_entries():
    missing = source_verifier._missing_configured_fields(
        "wa_dfw_habitat",
        {"PHS_TYPE"},
        {"PriorityArea_Desc"},
    )

    assert missing == set()
