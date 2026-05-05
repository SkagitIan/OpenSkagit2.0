from agent.adapters import arcgis, federal, web
from agent.catalog.sources import get_sources_for_domains


async def execute_step(step: dict) -> dict:
    sources = get_sources_for_domains([step["domain"]])
    if not sources:
        return {
            "success": False,
            "domain": step["domain"],
            "error": f"No source registered for domain: {step['domain']}",
        }

    source = sources[0]
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
        return {
            "success": False,
            "domain": step["domain"],
            "error": f"Unknown source type: {source_type}",
        }

    return {
        "source_id": source["id"],
        "source_name": source["name"],
        "domain": step["domain"],
        "success": result.get("success", False),
        "data": result.get("features", result.get("records", [])),
        "count": result.get("count", 0),
        "error": result.get("error"),
    }


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
