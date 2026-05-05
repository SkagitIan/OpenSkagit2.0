import json
import os
import sqlite3
from pathlib import Path
from typing import Optional


DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _deserialize(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["domains"] = json.loads(item.get("domains") or "[]")
    item["supports"] = json.loads(item.get("supports") or "[]")
    item["config"] = json.loads(item.get("config") or "{}")
    return item


def _ensure_seeded() -> None:
    if Path(DB_PATH).exists():
        return
    try:
        from catalog.seeds.seed import seed_local

        seed_local()
    except Exception:
        pass


def get_source(source_id: str) -> Optional[dict]:
    _ensure_seeded()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ? AND active = 1",
            (source_id,),
        ).fetchone()
    return _deserialize(row) if row else None


def get_sources_for_domains(domains: list[str]) -> list[dict]:
    _ensure_seeded()
    wanted = set(domains)
    return [source for source in list_sources() if wanted.intersection(source["domains"])]


def list_sources() -> list[dict]:
    _ensure_seeded()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sources WHERE active = 1 ORDER BY id").fetchall()
    return [_deserialize(row) for row in rows]
