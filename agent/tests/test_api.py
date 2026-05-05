from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from agent.main import app


client = TestClient(app)


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
        response = client.post("/ask", json={"question": "Tell me about parcel P48165"})
    job_id = response.json()["job_id"]
    job = client.get(f"/job/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "complete"


def test_ask_requires_question():
    response = client.post("/ask", json={"context": {}})
    assert response.status_code == 422
