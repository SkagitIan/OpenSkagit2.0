import os

import httpx


WEB_WORKER_URL = os.environ.get("WEB_WORKER_URL", "http://localhost:8788")


async def query(source: dict, query_type: str, params: dict) -> dict:
    config = source.get("config", {})
    form_params = _build_form_params(config, query_type, params)

    if not config.get("endpoint"):
        return {
            "success": False,
            "records": [],
            "count": 0,
            "error": f"Source {source['id']} has no configured endpoint",
        }

    payload = {
        "source_id": source["id"],
        "endpoint": config["endpoint"],
        "method": config.get("method", "POST"),
        "query_type": config.get("query_type", "form_post"),
        "params": form_params,
        "response_format": config.get("response_format", "html_table"),
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{WEB_WORKER_URL.rstrip('/')}/query", json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"success": False, "records": [], "count": 0, "error": str(exc)}


def _build_form_params(config: dict, query_type: str, params: dict) -> dict:
    if query_type == "query_by_parcel":
        key = config.get("parcel_param", "parcel")
        result = {key: params.get("parcel_id", "")}
        if config.get("searchby_param") and config.get("parcel_searchby_value"):
            result[config["searchby_param"]] = config["parcel_searchby_value"]
        return result
    if query_type == "query_by_owner":
        key = config.get("owner_param", "owner")
        result = {key: params.get("owner_name", "")}
        if config.get("searchby_param") and config.get("owner_searchby_value"):
            result[config["searchby_param"]] = config["owner_searchby_value"]
        return result
    if query_type == "query_by_name":
        key = config.get("name_param", "name")
        return {key: params.get("name", params.get("owner_name", ""))}
    return params
