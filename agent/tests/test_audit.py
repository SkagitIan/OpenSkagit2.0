from agent.audit import get_stats, log_query


def test_log_query_does_not_raise():
    log_query(
        job_id="job_test123",
        api_key_id="key_test",
        question="Tell me about P48165",
        entity="P48165",
        sources_queried=["skagit_parcels"],
        confidence="medium",
        duration_ms=1234,
    )


def test_log_query_handles_db_error_silently(monkeypatch):
    import agent.audit as audit_module

    monkeypatch.setattr(audit_module, "DB_PATH", "/nonexistent/path/db.sqlite")
    log_query("j", "k", "q", None, [], "low", 0)


def test_get_stats_returns_expected_shape():
    stats = get_stats(days=30)
    assert "total_queries" in stats
    assert "by_confidence" in stats
    assert "top_entities" in stats
    assert isinstance(stats["top_entities"], list)
