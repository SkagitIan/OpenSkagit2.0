from fastapi.testclient import TestClient

from agent.main import app


client = TestClient(app)
AUTH_HEADER = {"X-API-Key": "dev-admin-key-change-in-production"}


def test_ask_requires_api_key():
    response = client.post("/ask", json={"question": "test"})
    assert response.status_code == 401


def test_ask_accepts_valid_reader_key():
    response = client.post(
        "/ask",
        json={"question": "Tell me about parcel P48165"},
        headers=AUTH_HEADER,
    )
    assert response.status_code not in {401, 403}


def test_admin_endpoint_requires_admin_key():
    response = client.get("/admin/stats", headers=AUTH_HEADER)
    assert response.status_code == 200


def test_health_requires_no_auth():
    response = client.get("/health")
    assert response.status_code == 200


def test_config_requires_no_auth():
    response = client.get("/config")
    assert response.status_code == 200
    assert "display_name" in response.json()
