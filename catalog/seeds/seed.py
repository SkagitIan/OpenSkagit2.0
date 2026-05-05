"""Seed source metadata into local SQLite or production Cloudflare D1.

Usage
-----
Local (SQLite):
    python catalog/seeds/seed.py

Production (D1) — requires D1 credentials in environment:
    python catalog/seeds/seed.py --env production

D1 credentials can be set in your .env file or passed directly:
    D1_ACCOUNT_ID=...  D1_DATABASE_ID=...  D1_API_TOKEN=...  python catalog/seeds/seed.py --env production

Get credentials from:
  - Cloudflare dashboard → Workers & Pages → D1 → your database → Settings
  - OR Railway dashboard → your service → Variables (they're injected there automatically)
"""

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema.sql"
SEED_FILES = ["skagit.yaml", "skagit_web.yaml", "federal.yaml", "wa_state.yaml", "federal_gis.yaml"]

# Sources that existed in older catalog versions and should be deactivated.
RETIRED_SOURCES = [
    "skagit_treasurer",  # replaced by skagit_assessor_* sources
]

D1_API_BASE = os.environ.get("D1_API_BASE", "https://api.cloudflare.com/client/v4")


# ---------------------------------------------------------------------------
# Shared data loading
# ---------------------------------------------------------------------------

def load_sources() -> list[tuple[str, dict]]:
    """Return list of (source_id, source_dict) from all seed files."""
    sources = []
    for seed_file in SEED_FILES:
        seed_path = Path(__file__).with_name(seed_file)
        if not seed_path.exists():
            continue
        data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
        for source_id, source in data.get("sources", {}).items():
            sources.append((source_id, source))
    return sources


# ---------------------------------------------------------------------------
# Local SQLite
# ---------------------------------------------------------------------------

def seed_local() -> None:
    db_path = Path(os.environ.get("D1_LOCAL_PATH", str(ROOT / "local.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Seeding local SQLite: {db_path}")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _seed_api_key_local(conn)
        for source_id, source in load_sources():
            conn.execute(
                """
                INSERT INTO sources (id, name, type, base_url, domains, supports, config, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name,
                  type=excluded.type,
                  base_url=excluded.base_url,
                  domains=excluded.domains,
                  supports=excluded.supports,
                  config=excluded.config,
                  active=excluded.active
                """,
                (
                    source_id,
                    source["name"],
                    source["type"],
                    source["base_url"],
                    json.dumps(source["domains"]),
                    json.dumps(source["supports"]),
                    json.dumps(source.get("config") or {}),
                ),
            )
            print(f"  upserted: {source_id}")
        for retired_id in RETIRED_SOURCES:
            conn.execute("UPDATE sources SET active = 0 WHERE id = ?", (retired_id,))
            print(f"  deactivated: {retired_id}")
    print("Local seed complete.")


def _seed_api_key_local(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT count(*) FROM api_keys WHERE role = 'admin'").fetchone()[0]
    if existing:
        return
    raw_key = "dev-admin-key-change-in-production"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    conn.execute(
        "INSERT INTO api_keys (id, key_hash, name, role) VALUES (?, ?, ?, ?)",
        ("key_dev_admin", key_hash, "Dev Admin", "admin"),
    )
    print(f"  seeded dev admin key: {raw_key}")


# ---------------------------------------------------------------------------
# Cloudflare D1
# ---------------------------------------------------------------------------

def seed_d1() -> None:
    account_id = os.environ.get("D1_ACCOUNT_ID", "")
    database_id = os.environ.get("D1_DATABASE_ID", "")
    api_token = os.environ.get("D1_API_TOKEN", "")

    if not all([account_id, database_id, api_token]):
        raise SystemExit(
            "D1 credentials missing. Set D1_ACCOUNT_ID, D1_DATABASE_ID, and "
            "D1_API_TOKEN in your environment or .env file.\n\n"
            "Find them in:\n"
            "  - Cloudflare dashboard → Workers & Pages → D1 → your database\n"
            "  - OR Railway dashboard → your service → Variables"
        )

    print(f"Seeding Cloudflare D1 database: {database_id}")

    def execute(sql: str, params: list[Any] | None = None) -> None:
        url = f"{D1_API_BASE}/accounts/{account_id}/d1/database/{database_id}/raw"
        payload: dict[str, Any] = {"sql": sql}
        if params:
            payload["params"] = params
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
            )
        data = response.json()
        if not response.is_success or not data.get("success", False):
            errors = data.get("errors") or []
            detail = "; ".join(e.get("message", str(e)) for e in errors) or response.text
            raise RuntimeError(f"D1 error: {detail}")

    # Apply schema (split on ; since D1 doesn't accept multi-statement scripts)
    print("  applying schema...")
    for statement in _split_sql(SCHEMA_PATH.read_text(encoding="utf-8")):
        execute(statement)

    # Upsert sources
    for source_id, source in load_sources():
        execute(
            """
            INSERT INTO sources (id, name, type, base_url, domains, supports, config, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              type=excluded.type,
              base_url=excluded.base_url,
              domains=excluded.domains,
              supports=excluded.supports,
              config=excluded.config,
              active=excluded.active
            """,
            [
                source_id,
                source["name"],
                source["type"],
                source["base_url"],
                json.dumps(source["domains"]),
                json.dumps(source["supports"]),
                json.dumps(source.get("config") or {}),
            ],
        )
        print(f"  upserted: {source_id}")

    # Deactivate retired sources
    for retired_id in RETIRED_SOURCES:
        execute("UPDATE sources SET active = 0 WHERE id = ?", [retired_id])
        print(f"  deactivated: {retired_id}")

    print("D1 seed complete.")


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script into individual statements for D1."""
    statements = []
    current: list[str] = []
    in_string: str | None = None
    for char in sql:
        current.append(char)
        if char in {"'", '"'}:
            in_string = None if in_string == char else (char if in_string is None else in_string)
        if char == ";" and in_string is None:
            stmt = "".join(current).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return [s for s in statements if s]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Auto-load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Seed source metadata.")
    parser.add_argument(
        "--env",
        choices=["local", "production"],
        default="local",
        help="'local' seeds SQLite, 'production' seeds Cloudflare D1",
    )
    args = parser.parse_args()

    if args.env == "production":
        seed_d1()
    else:
        seed_local()


if __name__ == "__main__":
    main()
