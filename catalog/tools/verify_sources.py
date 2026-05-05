import asyncio
import json
import os
import sqlite3
from urllib.parse import urlparse

import httpx


DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")


async def check_source(client: httpx.AsyncClient, source: dict) -> dict:
    base_url = source["base_url"].rstrip("/")
    url = f"{base_url}?f=json"
    result = {
        "id": source["id"],
        "name": source["name"],
        "reachable": False,
        "spatial_ref": "",
        "layer_count": "",
        "error": "",
    }
    try:
        response = await client.get(url, headers={"user-agent": "Mozilla/5.0 OpenSkagitPhase3"})
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError(data["error"].get("message", "ArcGIS error"))
        result["reachable"] = True
        result["spatial_ref"] = _spatial_ref(data)
        result["layer_count"] = str(len(data.get("layers") or []))
    except Exception as exc:
        result["error"] = str(exc)
        if source["type"] == "web":
            result["error"] = f"web source, JSON verification not expected ({urlparse(base_url).netloc})"
    return result


async def main() -> None:
    sources = _load_sources()
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(check_source(client, source) for source in sources),
            return_exceptions=True,
        )
    rows = [item if isinstance(item, dict) else _exception_row(item) for item in results]
    _print_table(rows)


def _load_sources() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, type, base_url, config FROM sources WHERE active=1 ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def _spatial_ref(data: dict) -> str:
    sr = (
        data.get("spatialReference")
        or data.get("fullExtent", {}).get("spatialReference")
        or data.get("extent", {}).get("spatialReference")
        or {}
    )
    value = sr.get("wkid") or sr.get("latestWkid")
    return str(value or "")


def _exception_row(exc: Exception) -> dict:
    return {
        "id": "unknown",
        "name": "",
        "reachable": False,
        "spatial_ref": "",
        "layer_count": "",
        "error": str(exc),
    }


def _print_table(rows: list[dict]) -> None:
    print(f"{'source_id':<30} {'reachable':<10} {'spatial_ref':<12} {'layers':<7} error")
    print("-" * 95)
    for row in rows:
        reachable = "yes" if row["reachable"] else "no"
        print(
            f"{row['id']:<30} {reachable:<10} {row['spatial_ref']:<12} "
            f"{row['layer_count']:<7} {row['error'][:80]}"
        )


if __name__ == "__main__":
    asyncio.run(main())
