import os

import httpx


ARCGIS_WORKER_URL = os.environ.get("ARCGIS_WORKER_URL", "http://localhost:8787")


async def query(source: dict, query_type: str, params: dict) -> dict:
    config = source.get("config", {})
    payload = {
        "base_url": source["base_url"],
        "layer_id": config.get("layer_id", 0),
        "parcel_field": config.get("parcel_field", "PARCELID"),
        "query_type": query_type,
        "params": params,
    }
    if config.get("in_sr"):
        payload["in_sr"] = config["in_sr"]
    if config.get("server_type"):
        payload["server_type"] = config["server_type"]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{ARCGIS_WORKER_URL.rstrip('/')}/query", json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {
            "success": False,
            "features": [],
            "count": 0,
            "error": str(exc),
            "source_url": source.get("base_url", ""),
        }
