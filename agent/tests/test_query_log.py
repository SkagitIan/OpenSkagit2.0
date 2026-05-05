import sqlite3

from agent import db, query_log


def test_query_log_records_failed_attempt(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "D1_ACCOUNT_ID", "")
    monkeypatch.setattr(db, "D1_DATABASE_ID", "")
    monkeypatch.setattr(db, "D1_API_TOKEN", "")

    query_id = query_log.log_attempt(
        job_id="job_1",
        step={"source_id": "sedro_woolley_permits", "domain": "permits", "query_type": "by_date"},
        source={"id": "sedro_woolley_permits", "name": "Sedro-Woolley iWorQ Permits"},
        params={"searchField": "permit_dt_range"},
        result={
            "success": False,
            "count": 0,
            "source_url": "https://example.test/permits",
            "raw_excerpt": "captcha",
            "error": "HTTP 403",
        },
        started_at=query_log.start_timer(),
    )

    detail = query_log.get_query(query_id)

    assert detail["status"] == "failed"
    assert detail["query_params"] == {"searchField": "permit_dt_range"}
    assert detail["raw_excerpt"] == "captcha"
    assert detail["error"] == "HTTP 403"


def test_query_log_attaches_case_file_id(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "D1_ACCOUNT_ID", "")
    monkeypatch.setattr(db, "D1_DATABASE_ID", "")
    monkeypatch.setattr(db, "D1_API_TOKEN", "")

    query_log.log_attempt(
        job_id="job_1",
        step={"source_id": "source_one", "domain": "permits", "query_type": "by_date"},
        source={"id": "source_one", "name": "Source One"},
        params={},
        result={"success": True, "count": 0, "records": []},
        started_at=query_log.start_timer(),
    )
    query_log.attach_case_file_id("job_1", "cf_1")

    with sqlite3.connect(db_path) as conn:
        case_file_id = conn.execute("SELECT case_file_id FROM queries").fetchone()[0]

    assert case_file_id == "cf_1"
