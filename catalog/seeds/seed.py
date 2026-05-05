import argparse
import json
import os
import sqlite3
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema.sql"
SEED_FILES = ["skagit.yaml", "skagit_web.yaml", "federal.yaml", "wa_state.yaml", "federal_gis.yaml"]


def seed_local() -> None:
    db_path = Path(os.environ.get("D1_LOCAL_PATH", str(ROOT / "local.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for seed_file in SEED_FILES:
            seed_path = Path(__file__).with_name(seed_file)
            if not seed_path.exists():
                continue
            data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
            for source_id, source in data.get("sources", {}).items():
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed source metadata.")
    parser.add_argument("--env", choices=["local", "production"], default="local")
    args = parser.parse_args()
    if args.env == "production":
        raise SystemExit("Production D1 seeding should run through wrangler d1 execute in Phase 1.")
    seed_local()


if __name__ == "__main__":
    main()
