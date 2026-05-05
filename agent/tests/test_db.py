import httpx
import json
import respx

from agent import db


def test_db_uses_sqlite_when_d1_env_missing(monkeypatch):
    monkeypatch.setattr(db, "D1_ACCOUNT_ID", "")
    monkeypatch.setattr(db, "D1_DATABASE_ID", "")
    monkeypatch.setattr(db, "D1_API_TOKEN", "")

    assert db.using_d1() is False


@respx.mock
def test_d1_fetchall_maps_raw_rows(monkeypatch):
    monkeypatch.setattr(db, "D1_ACCOUNT_ID", "acct")
    monkeypatch.setattr(db, "D1_DATABASE_ID", "dbid")
    monkeypatch.setattr(db, "D1_API_TOKEN", "token")
    monkeypatch.setattr(db, "D1_API_BASE", "https://api.cloudflare.test/client/v4")
    route = respx.post("https://api.cloudflare.test/client/v4/accounts/acct/d1/database/dbid/raw").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "results": {
                            "columns": ["id", "name"],
                            "rows": [["src_1", "Source One"]],
                        }
                    }
                ],
            },
        )
    )

    rows = db.fetchall("SELECT id, name FROM sources WHERE id = ?", ("src_1",))

    assert rows == [{"id": "src_1", "name": "Source One"}]
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer token"
    assert json.loads(sent.content) == {"sql": "SELECT id, name FROM sources WHERE id = ?", "params": ["src_1"]}
