from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from agent.main import app


client = TestClient(app)
AUTH_HEADER = {"X-API-Key": "dev-admin-key-change-in-production"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ask_returns_job_id():
    mock_response = {
        "job_id": "test-job-id",
        "status": "complete",
        "question": "Tell me about parcel P48165",
        "answer": "P48165 is a 1.2 acre parcel...",
        "confidence": "medium",
        "evidence": [],
        "missing": [],
        "sources_queried": [],
        "case_file_id": "cf_abc123",
        "error": None,
    }
    with patch("agent.main.run_ask", new=AsyncMock(return_value=mock_response)):
        response = client.post(
            "/ask",
            json={"question": "Tell me about parcel P48165", "context": {"county": "skagit"}},
            headers=AUTH_HEADER,
        )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ["complete", "pending"]


def test_job_returns_saved_result():
    mock_response = {
        "job_id": "test-job-id",
        "status": "complete",
        "question": "Tell me about parcel P48165",
        "answer": "According to Skagit County Parcels, parcel P48165 has evidence.",
        "confidence": "medium",
        "evidence": [],
        "missing": [],
        "sources_queried": [],
        "case_file_id": "cf_abc123",
        "error": None,
    }
    with patch("agent.main.run_ask", new=AsyncMock(return_value=mock_response)):
        response = client.post("/ask", json={"question": "Tell me about parcel P48165"}, headers=AUTH_HEADER)
    job_id = response.json()["job_id"]
    job = client.get(f"/job/{job_id}", headers=AUTH_HEADER)
    assert job.status_code == 200
    assert job.json()["status"] == "complete"


def test_ask_requires_question():
    response = client.post("/ask", json={"context": {}}, headers=AUTH_HEADER)
    assert response.status_code == 422


def test_admin_queries_returns_logged_attempts():
    response = client.get("/admin/queries?limit=5", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert "queries" in data
    assert "total" in data


def test_ask_failed_source_writes_query_diagnostics():
    plan = {
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
                "reason": "Count active permits",
            }
        ],
        "ambiguous": False,
        "clarification_needed": None,
    }
    adapter_result = {
        "success": False,
        "records": [],
        "count": 0,
        "source_url": "https://sedro-woolley.portal.iworq.net/SEDRO-WOOLLEY/permits/601",
        "raw_excerpt": "captcha required",
        "error": "HTTP 403",
    }
    with patch("agent.main.planner.create_plan", new=AsyncMock(return_value=plan)):
        with patch("agent.dispatcher.web.query", new=AsyncMock(return_value=adapter_result)):
            response = client.post(
                "/ask",
                json={"question": "How many active permits are in Sedro-Woolley?"},
                headers=AUTH_HEADER,
            )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    queries = client.get(f"/admin/queries?job_id={job_id}", headers=AUTH_HEADER)
    assert queries.status_code == 200
    items = queries.json()["queries"]
    assert len(items) == 1
    assert items[0]["source_id"] == "sedro_woolley_permits"
    assert items[0]["status"] == "failed"

    detail = client.get(f"/admin/queries/{items[0]['id']}", headers=AUTH_HEADER)
    assert detail.status_code == 200
    assert detail.json()["raw_excerpt"] == "captcha required"
