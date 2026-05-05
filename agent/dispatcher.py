from agent.adapters import arcgis, federal, web
from agent.catalog.context import source_supports_query
from agent.catalog.sources import get_source, get_sources_for_domains
from agent import query_log


async def execute_step(step: dict, job_id: str | None = None) -> dict:
    started_at = query_log.start_timer()
    source = _select_source(step)
    if not source:
        result = {
            "success": False,
            "domain": step["domain"],
            "error": _source_error(step),
        }
        _log_if_job(job_id, step, source, {}, result, started_at)
        return result

    if step.get("domain") not in source.get("domains", []):
        result = {
            "success": False,
            "domain": step["domain"],
            "source_id": source["id"],
            "error": f"Source {source['id']} does not support domain: {step['domain']}",
        }
        _log_if_job(job_id, step, source, {}, result, started_at)
        return result

    if not source_supports_query(source, step["query_type"]):
        result = {
            "success": False,
            "domain": step["domain"],
            "source_id": source["id"],
            "error": f"Source {source['id']} does not support query_type: {step['query_type']}",
        }
        _log_if_job(job_id, step, source, {}, result, started_at)
        return result

    params = _build_params(step)
    source_type = source["type"]

    if source_type == "arcgis_rest":
        result = await arcgis.query(source=source, query_type=step["query_type"], params=params)
    elif source_type == "web":
        result = await web.query(
            source=source,
            query_type=f"query_{step['query_type']}",
            params=params,
        )
    elif source_type == "rest_api":
        result = await _dispatch_rest_api(source, step, params)
    else:
        result = {
            "success": False,
            "domain": step["domain"],
            "error": f"Unknown source type: {source_type}",
        }
        _log_if_job(job_id, step, source, params, result, started_at)
        return result

    normalized = {
        "source_id": source["id"],
        "source_name": source["name"],
        "domain": step["domain"],
        "success": result.get("success", False),
        "data": result.get("features", result.get("records", [])),
        "count": result.get("count", 0),
        "error": result.get("error"),
        "source_url": result.get("source_url"),
        "source_urls": result.get("source_urls", []),
        "http_status": result.get("http_status"),
        "raw_excerpt": result.get("raw_excerpt"),
    }
    _log_if_job(job_id, step, source, params, result, started_at)
    return normalized


def _select_source(step: dict) -> dict | None:
    source_id = step.get("source_id")
    if source_id:
        return get_source(source_id)
    sources = get_sources_for_domains([step["domain"]])
    return sources[0] if sources else None


def _source_error(step: dict) -> str:
    if step.get("source_id"):
        return f"No active source registered with source_id: {step['source_id']}"
    return f"No source registered for domain: {step['domain']}"


def _log_if_job(job_id: str | None, step: dict, source: dict | None, params: dict, result: dict, started_at: float) -> None:
    if not job_id:
        return
    try:
        query_log.log_attempt(
            job_id=job_id,
            step=step,
            source=source,
            params=params,
            result=result,
            started_at=started_at,
        )
    except Exception:
        pass


async def _dispatch_rest_api(source: dict, step: dict, params: dict) -> dict:
    if source["id"] == "federal_usaspending":
        return await federal.query_usaspending(
            source["config"]["awards_endpoint"],
            _build_usaspending_payload(step, params),
        )
    if source["id"] == "federal_sam":
        return await federal.query_sam(params)
    return {
        "success": False,
        "records": [],
        "count": 0,
        "error": f"No handler for rest_api source: {source['id']}",
    }


def _build_params(step: dict) -> dict:
    entity = step.get("entity", "")
    query_type = step.get("query_type", "by_parcel")
    if query_type == "by_parcel":
        return {
            "parcel_id": entity,
            "where": f"PARCELID = '{entity}'",
            "out_fields": ["*"],
            "return_geometry": True,
        }
    if query_type == "by_address":
        return {
            "address": entity,
            "search": entity,
            "where": f"SITEADDRESS LIKE '%{entity}%'",
            "out_fields": ["*"],
        }
    if query_type == "by_owner":
        return {"owner_name": entity}
    if query_type == "by_name":
        return {"name": entity, "owner_name": entity}
    if query_type == "by_date":
        return {
            "start_date": step.get("start_date", ""),
            "end_date": step.get("end_date", ""),
            "search": step.get("search", ""),
            "_aggregate_mode": step.get("aggregate_mode", ""),
            "_status_filter": step.get("status_filter", ""),
        }
    if query_type == "by_permit":
        return {"permit_number": entity, "search": entity}
    if query_type == "by_geometry":
        return {"geometry": step.get("geometry"), "out_fields": ["*"]}
    return {"where": "1=1", "return_count": 5, "out_fields": ["*"]}


def _build_usaspending_payload(step: dict, params: dict) -> dict:
    return {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],
            "recipient_search_text": [params.get("name") or params.get("parcel_id", "")],
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Description"],
        "page": 1,
        "limit": 10,
        "sort": "Award Amount",
        "order": "desc",
    }
