import json
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from agent import db

DB_PATH = db.DB_PATH


def _ensure_jobs_table() -> None:
    db.execute(
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_job(row: dict) -> dict:
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
    _ensure_jobs_table()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    db.execute(
        """
        INSERT INTO jobs (id, status, created_at, result, error)
        VALUES (?, 'pending', ?, NULL, NULL)
        """,
        (job_id, _now()),
    )
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    _ensure_jobs_table()
    row = db.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return _decode_job(row) if row else None


def complete_job(job_id: str, result: dict) -> None:
    _ensure_jobs_table()
    db.execute(
        """
        UPDATE jobs
        SET status = 'complete', result = ?, error = NULL, completed_at = ?
        WHERE id = ?
        """,
        (json.dumps(result), _now(), job_id),
    )


def record_job(job_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    _ensure_jobs_table()
    completed_at = _now() if status in {"complete", "error", "failed"} else None
    db.execute(
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
    _ensure_jobs_table()
    db.execute(
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
