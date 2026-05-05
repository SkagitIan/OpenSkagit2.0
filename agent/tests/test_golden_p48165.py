import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.main import app


CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


@pytest.mark.skipif(os.environ.get("RUN_LIVE_GOLDEN") != "1", reason="requires local Worker and live Skagit GIS")
def test_live_p48165_matches_golden_fixture():
    fixture = json.loads(
        Path("agent/tests/fixtures/p48165_expected.json").read_text(encoding="utf-8")
    )
    client = TestClient(app)
    response = client.post(
        "/ask",
        json={"question": fixture["question"], "context": {"county": "skagit", "state": "wa"}},
        headers={"X-API-Key": "dev-admin-key-change-in-production"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert CONFIDENCE_ORDER[data["confidence"]] >= CONFIDENCE_ORDER[fixture["confidence_min"]]
    assert set(fixture["required_sources"]).issubset(set(data["sources_queried"]))
    evidence_by_source = {item["source_id"]: item["data"] for item in data["evidence"]}
    parcel_data = evidence_by_source["skagit_parcels"]
    for field in fixture["required_evidence_fields"]:
        assert field in parcel_data
        assert parcel_data[field] not in [None, ""]
    for phrase in fixture["answer_must_contain"]:
        assert phrase in data["answer"]
    for phrase in fixture["answer_must_not_contain"]:
        assert phrase.lower() not in data["answer"].lower()
