from parcelbook_ai.service import ask_parcels


def test_ask_parcels_fallback_mocked(monkeypatch):
    def fake_execute(sql, limit=100):
        return {"sql": sql, "row_count": 1, "rows": [{"parcel_number": "P1", "situs_address": "1 Main", "owner_name": "Owner"}], "caveats": ["caveat"]}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("parcelbook_ai.duckdb_tools.execute_parcel_sql", fake_execute)
    answer = ask_parcels("Find older houses on big lots", limit=1)
    assert answer.row_count == 1
    assert answer.results[0].parcel_number == "P1"


def test_zoning_mcp_unavailable_does_not_crash_parcel_first(monkeypatch):
    def fake_execute(sql, limit=100):
        return {"sql": sql, "row_count": 0, "rows": [], "caveats": ["caveat"]}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ZONING_MCP_ENABLED", "false")
    monkeypatch.setattr("parcelbook_ai.duckdb_tools.execute_parcel_sql", fake_execute)
    answer = ask_parcels("Find ADU candidates in Mount Vernon", limit=1)
    assert answer.mode == "parcel_first"
    assert answer.zoning_was_used is False
    assert any("Zoning MCP was not available" in caveat for caveat in answer.general_caveats)
