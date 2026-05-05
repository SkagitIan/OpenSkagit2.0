import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from agent import db

DB_PATH = db.DB_PATH
ROLE_HIERARCHY = ["reader", "writer", "admin"]

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_key(raw_key: str | None, required_role: str = "reader") -> dict:
    if not raw_key:
        raise HTTPException(status_code=401, detail="API key required")
    if required_role not in ROLE_HIERARCHY:
        raise HTTPException(status_code=500, detail="Invalid role configuration")

    row = db.fetchone(
        "SELECT * FROM api_keys WHERE key_hash = ? AND active = 1",
        (_hash_key(raw_key),),
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")

    key_role = row["role"]
    if key_role not in ROLE_HIERARCHY or ROLE_HIERARCHY.index(key_role) < ROLE_HIERARCHY.index(required_role):
        raise HTTPException(status_code=403, detail=f"Role '{key_role}' cannot access this endpoint")

    db.execute(
        "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    return dict(row)


def require_reader(api_key: str = Security(api_key_header)) -> dict:
    return verify_key(api_key, "reader")


def require_writer(api_key: str = Security(api_key_header)) -> dict:
    return verify_key(api_key, "writer")


def require_admin(api_key: str = Security(api_key_header)) -> dict:
    return verify_key(api_key, "admin")
