import json
from typing import Optional

from agent import db

DB_PATH = db.DB_PATH


def _deserialize(row: dict) -> dict:
    item = dict(row)
    item["domains"] = json.loads(item.get("domains") or "[]")
    item["supports"] = json.loads(item.get("supports") or "[]")
    item["config"] = json.loads(item.get("config") or "{}")
    return item


def _ensure_seeded() -> None:
    db.ensure_local_seeded()


def get_source(source_id: str) -> Optional[dict]:
    _ensure_seeded()
    row = db.fetchone(
        "SELECT * FROM sources WHERE id = ? AND active = 1",
        (source_id,),
    )
    return _deserialize(row) if row else None


def get_sources_for_domains(domains: list[str]) -> list[dict]:
    _ensure_seeded()
    wanted = set(domains)
    return [source for source in list_sources() if wanted.intersection(source["domains"])]


def list_sources() -> list[dict]:
    _ensure_seeded()
    rows = db.fetchall("SELECT * FROM sources WHERE active = 1 ORDER BY id")
    return [_deserialize(row) for row in rows]
