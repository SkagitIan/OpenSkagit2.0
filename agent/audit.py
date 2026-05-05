import json
import os
import sqlite3
import uuid
from typing import Optional


DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")


def log_query(
    job_id: str,
    api_key_id: str,
    question: str,
    entity: Optional[str],
    sources_queried: list[str],
    confidence: str,
    duration_ms: int,
    ip_address: Optional[str] = None,
) -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO audit_log
                  (id, job_id, api_key_id, question, entity, sources_queried, confidence, duration_ms, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"al_{uuid.uuid4().hex[:12]}",
                    job_id,
                    api_key_id,
                    question,
                    entity,
                    json.dumps(sources_queried),
                    confidence,
                    duration_ms,
                    ip_address,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_stats(days: int = 30) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute(
            "SELECT count(*) as n FROM audit_log WHERE created_at > datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()["n"]
        by_confidence = conn.execute(
            """
            SELECT confidence, count(*) as n FROM audit_log
            WHERE created_at > datetime('now', ?)
            GROUP BY confidence
            """,
            (f"-{days} days",),
        ).fetchall()
        top_entities = conn.execute(
            """
            SELECT entity, count(*) as n FROM audit_log
            WHERE entity IS NOT NULL AND created_at > datetime('now', ?)
            GROUP BY entity ORDER BY n DESC LIMIT 10
            """,
            (f"-{days} days",),
        ).fetchall()
        avg_duration = conn.execute(
            "SELECT avg(duration_ms) as avg_ms FROM audit_log WHERE created_at > datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()["avg_ms"]
        return {
            "period_days": days,
            "total_queries": total,
            "by_confidence": {r["confidence"]: r["n"] for r in by_confidence},
            "top_entities": [{"entity": r["entity"], "count": r["n"]} for r in top_entities],
            "avg_duration_ms": round(avg_duration or 0, 1),
        }
    finally:
        conn.close()
