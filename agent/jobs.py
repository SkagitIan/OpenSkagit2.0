import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from agent.catalog.sources import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              status TEXT DEFAULT 'pending',
              result TEXT,
              error TEXT,
              created_at TEXT DEFAULT (datetime('now')),
              completed_at TEXT
            )
            """
        )
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_job(row: sqlite3.Row) -> dict:
    result = row["result"]
    return {
        "job_id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "result": json.loads(result) if result else None,
        "error": row["error"],
    }


def create_job() -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, status, created_at, result, error)
            VALUES (?, 'pending', ?, NULL, NULL)
            """,
            (job_id, _now()),
        )
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode_job(row) if row else None


def complete_job(job_id: str, result: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'complete', result = ?, error = NULL, completed_at = ?
            WHERE id = ?
            """,
            (json.dumps(result), _now(), job_id),
        )


def record_job(job_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    completed_at = _now() if status in {"complete", "error", "failed"} else None
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, status, result, error, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              status=excluded.status,
              result=excluded.result,
              error=excluded.error,
              completed_at=excluded.completed_at
            """,
            (
                job_id,
                status,
                json.dumps(result) if result is not None else None,
                error,
                _now(),
                completed_at,
            ),
        )


def fail_job(job_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'error', error = ?, completed_at = ?
            WHERE id = ?
            """,
            (error, _now(), job_id),
        )


async def run_job(job_id: str, task: Callable[[], Awaitable[dict]]) -> dict:
    try:
        result = await task()
        complete_job(job_id, result)
        return result
    except Exception as exc:
        fail_job(job_id, str(exc))
        raise
