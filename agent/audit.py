import json
import uuid
from typing import Optional

from agent import db

DB_PATH = db.DB_PATH


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
        db.execute(
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
    except Exception:
        pass


def get_stats(days: int = 30) -> dict:
    total = db.fetchone(
        "SELECT count(*) as n FROM audit_log WHERE created_at > datetime('now', ?)",
        (f"-{days} days",),
    )["n"]
    by_confidence = db.fetchall(
        """
        SELECT confidence, count(*) as n FROM audit_log
        WHERE created_at > datetime('now', ?)
        GROUP BY confidence
        """,
        (f"-{days} days",),
    )
    top_entities = db.fetchall(
        """
        SELECT entity, count(*) as n FROM audit_log
        WHERE entity IS NOT NULL AND created_at > datetime('now', ?)
        GROUP BY entity ORDER BY n DESC LIMIT 10
        """,
        (f"-{days} days",),
    )
    avg_duration = db.fetchone(
        "SELECT avg(duration_ms) as avg_ms FROM audit_log WHERE created_at > datetime('now', ?)",
        (f"-{days} days",),
    )["avg_ms"]
    return {
        "period_days": days,
        "total_queries": total,
        "by_confidence": {r["confidence"]: r["n"] for r in by_confidence},
        "top_entities": [{"entity": r["entity"], "count": r["n"]} for r in top_entities],
        "avg_duration_ms": round(avg_duration or 0, 1),
    }
