import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agent import db


RAW_EXCERPT_LIMIT = 4000
RESULT_LIMIT = 12000


QUERY_COLUMNS = {
    "case_file_id": "TEXT",
    "source_name": "TEXT",
    "domain": "TEXT",
    "query_type": "TEXT",
    "success": "INTEGER DEFAULT 0",
    "count": "INTEGER DEFAULT 0",
    "source_url": "TEXT",
    "source_urls": "TEXT",
    "http_status": "INTEGER",
    "raw_excerpt": "TEXT",
}


def start_timer() -> float:
    return time.monotonic()


def log_attempt(
    *,
    job_id: str,
    step: dict,
    source: Optional[dict],
    params: dict,
    result: Optional[dict],
    started_at: float,
    case_file_id: Optional[str] = None,
) -> str:
    ensure_query_schema()
    query_id = f"qr_{uuid.uuid4().hex[:12]}"
    success = bool(result and result.get("success", False))
    count = int(result.get("count", 0) if result else 0)
    status = "success" if success and count > 0 else "empty" if success else "failed"
    result_summary = _result_summary(result or {})
    db.execute(
        """
        INSERT INTO queries
          (id, job_id, case_file_id, source_id, source_name, domain, query_type,
           query_params, result, status, success, count, source_url, source_urls,
           http_status, raw_excerpt, error, duration_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            query_id,
            job_id,
            case_file_id,
            step.get("source_id") or (source or {}).get("id") or "",
            (source or {}).get("name"),
            step.get("domain"),
            step.get("query_type"),
            _to_json(params),
            _cap(_to_json(result_summary), RESULT_LIMIT),
            status,
            1 if success else 0,
            count,
            (result or {}).get("source_url"),
            _to_json((result or {}).get("source_urls") or []),
            (result or {}).get("http_status"),
            _cap(str((result or {}).get("raw_excerpt") or ""), RAW_EXCERPT_LIMIT),
            (result or {}).get("error"),
            int((time.monotonic() - started_at) * 1000),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return query_id


def list_queries(
    *,
    job_id: Optional[str] = None,
    case_file_id: Optional[str] = None,
    source_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    ensure_query_schema()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where = ["1 = 1"]
    params: list[Any] = []
    if job_id:
        where.append("job_id = ?")
        params.append(job_id)
    if case_file_id:
        where.append("case_file_id = ?")
        params.append(case_file_id)
    if source_id:
        where.append("source_id = ?")
        params.append(source_id)
    if status:
        where.append("status = ?")
        params.append(status)
    where_sql = " AND ".join(where)
    total = db.fetchone(f"SELECT count(*) as n FROM queries WHERE {where_sql}", params)["n"]
    rows = db.fetchall(
        f"""
        SELECT id, job_id, case_file_id, source_id, source_name, domain, query_type,
               status, success, count, source_url, http_status, error, duration_ms, created_at
        FROM queries
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )
    return {"total": total, "limit": limit, "offset": offset, "queries": [_coerce(row) for row in rows]}


def get_query(query_id: str) -> Optional[dict]:
    ensure_query_schema()
    row = db.fetchone("SELECT * FROM queries WHERE id = ?", (query_id,))
    if not row:
        return None
    item = _coerce(row)
    item["query_params"] = _loads(item.get("query_params"), {})
    item["result"] = _loads(item.get("result"), {})
    item["source_urls"] = _loads(item.get("source_urls"), [])
    return item


def attach_case_file_id(job_id: str, case_file_id: str) -> None:
    ensure_query_schema()
    db.execute("UPDATE queries SET case_file_id = ? WHERE job_id = ?", (case_file_id, job_id))


def ensure_query_schema() -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS queries (
          id TEXT PRIMARY KEY,
          job_id TEXT NOT NULL,
          case_file_id TEXT,
          source_id TEXT NOT NULL,
          source_name TEXT,
          domain TEXT,
          query_type TEXT,
          query_params TEXT NOT NULL,
          result TEXT,
          status TEXT DEFAULT 'pending',
          success INTEGER DEFAULT 0,
          count INTEGER DEFAULT 0,
          source_url TEXT,
          source_urls TEXT,
          http_status INTEGER,
          raw_excerpt TEXT,
          error TEXT,
          duration_ms INTEGER,
          created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    if not db.using_d1():
        existing = {row["name"] for row in db.fetchall("PRAGMA table_info(queries)")}
        for column, spec in QUERY_COLUMNS.items():
            if column not in existing:
                db.execute(f"ALTER TABLE queries ADD COLUMN {column} {spec}")
    for statement in [
        "CREATE INDEX IF NOT EXISTS idx_queries_job ON queries(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_queries_case ON queries(case_file_id)",
        "CREATE INDEX IF NOT EXISTS idx_queries_source ON queries(source_id)",
        "CREATE INDEX IF NOT EXISTS idx_queries_status ON queries(status)",
    ]:
        db.execute(statement)


def _result_summary(result: dict) -> dict:
    records = result.get("features", result.get("records", []))
    return {
        "success": result.get("success", False),
        "count": result.get("count", 0),
        "source_url": result.get("source_url"),
        "source_urls": result.get("source_urls", []),
        "http_status": result.get("http_status"),
        "error": result.get("error"),
        "records_preview": records[:3] if isinstance(records, list) else records,
    }


def _coerce(row: dict) -> dict:
    item = dict(row)
    if "success" in item:
        item["success"] = bool(item["success"])
    return item


def _to_json(value: Any) -> str:
    return json.dumps(value, default=str)


def _loads(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _cap(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"
