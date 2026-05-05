import os

import httpx


SAM_API_KEY = os.environ.get("SAM_API_KEY", "")


async def query_usaspending(endpoint: str, payload: dict) -> dict:
    base = "https://api.usaspending.gov/api/v2"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{base}{endpoint}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "records": data.get("results", []),
                "count": data.get("page_metadata", {}).get("total", 0),
                "source_url": f"{base}{endpoint}",
            }
    except Exception as exc:
        return {"success": False, "records": [], "count": 0, "error": str(exc)}


async def query_sam(params: dict) -> dict:
    if not SAM_API_KEY:
        return {
            "success": False,
            "records": [],
            "count": 0,
            "error": "SAM_API_KEY not configured",
        }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://api.sam.gov/entity-information/v3/entities",
                params={**params, "api_key": SAM_API_KEY},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "records": data.get("entityData", []),
                "count": data.get("totalRecords", 0),
                "source_url": "https://api.sam.gov/entity-information/v3/entities",
            }
    except Exception as exc:
        return {"success": False, "records": [], "count": 0, "error": str(exc)}
