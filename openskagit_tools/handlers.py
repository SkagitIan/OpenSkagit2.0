from __future__ import annotations

from typing import Any, Callable

from assessor_mcp import services as assessor_services
from context_mcp import services as context_services
from gis_mcp import services as gis_services
from zoning_mcp import services as zoning_services

from .contracts import result_envelope
from .registry import get_tool_contract


def _result(
    tool_name: str,
    data: Any,
    *,
    warnings: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    return result_envelope(data, contract=get_tool_contract(tool_name), warnings=warnings, errors=errors, as_of=as_of)


def parcel_search(query: str, limit: int = 10) -> dict[str, Any]:
    return _result("parcel_search", assessor_services.search_parcels(query, limit))


def parcel_get_summary(parcel_id: str) -> dict[str, Any]:
    return _result("parcel_get_summary", assessor_services.get_parcel_details(parcel_id))


def parcel_get_history(parcel_id: str) -> dict[str, Any]:
    return _result("parcel_get_history", assessor_services.get_parcel_history(parcel_id))


def parcel_get_sales(parcel_id: str) -> dict[str, Any]:
    return _result("parcel_get_sales", assessor_services.get_parcel_sales(parcel_id))


def parcel_get_land(parcel_id: str) -> dict[str, Any]:
    return _result("parcel_get_land", assessor_services.get_parcel_land(parcel_id))


def parcel_get_improvements(parcel_id: str) -> dict[str, Any]:
    return _result("parcel_get_improvements", assessor_services.get_parcel_improvements(parcel_id))


def parcel_get_permits(parcel_id: str) -> dict[str, Any]:
    return _result("parcel_get_permits", assessor_services.get_parcel_permits(parcel_id))


def parcel_get_tax_detail(parcel_id: str, year: int | None = None) -> dict[str, Any]:
    return _result("parcel_get_tax_detail", assessor_services.get_parcel_tax_detail(parcel_id, year))


def parcel_get_full_report(parcel_id: str) -> dict[str, Any]:
    data = assessor_services.get_full_parcel_report(parcel_id)
    warnings = ["One or more live parcel sections failed; inspect data.errors."] if data.get("errors") else []
    return _result("parcel_get_full_report", data, warnings=warnings)


def gis_list_layers() -> dict[str, Any]:
    return _result("gis_list_layers", gis_services.list_gis_layers())


def gis_get_layer_metadata(layer: str) -> dict[str, Any]:
    return _result("gis_get_layer_metadata", gis_services.get_gis_layer_metadata(layer))


def gis_get_parcel(parcel_id: str, include_geometry: bool = True) -> dict[str, Any]:
    return _result("gis_get_parcel", gis_services.get_parcel_gis(parcel_id, include_geometry))


def gis_get_overlays(
    parcel_id: str,
    bundles: str | list[str] | None = None,
    layers: str | list[str] | None = None,
    include_parcel_geometry: bool = True,
) -> dict[str, Any]:
    data = gis_services.get_parcel_overlays(parcel_id, bundles, layers, include_parcel_geometry)
    failed = [row.get("layer", "unknown") for row in data.get("overlays", []) if row.get("status") != "ok"]
    warnings = [f"Some overlay queries failed: {', '.join(failed)}"] if failed else []
    return _result("gis_get_overlays", data, warnings=warnings)


def gis_query_layer(layer: str, where: str = "1=1", limit: int = 10, include_geometry: bool = False) -> dict[str, Any]:
    return _result("gis_query_layer", gis_services.query_gis_layer(layer, where, limit, include_geometry))


def _context_result(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    status = data.get("status")
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    if data.get("note"):
        warnings.append(str(data["note"]))
    if status == "partial":
        warnings.append("One or more upstream context levels failed; inspect data.errors.")
    elif status == "error":
        errors.append(
            {
                "code": "upstream_context_error",
                "message": str(data.get("error") or "Context source failed."),
                "stage": data.get("stage"),
            }
        )
    release = data.get("release")
    as_of = release.get("years") if isinstance(release, dict) else None
    return _result(tool_name, data, warnings=warnings, errors=errors, as_of=as_of)


def context_get_census(parcel_id: str) -> dict[str, Any]:
    return _context_result("context_get_census", context_services.get_census_context(parcel_id))


def context_get_soils(parcel_id: str) -> dict[str, Any]:
    return _context_result("context_get_soils", context_services.get_soils_context(parcel_id))


def zoning_resolve_parcel(parcel_id: str | None = None, address: str | None = None) -> dict[str, Any]:
    return _result("zoning_resolve_parcel", zoning_services.resolve_parcel(parcel_id=parcel_id, address=address))


def zoning_get_profile(jurisdiction: str, zone_code: str) -> dict[str, Any]:
    return _result("zoning_get_profile", zoning_services.get_zone_profile(jurisdiction, zone_code))


def zoning_lookup_use(jurisdiction: str, zone_code: str, proposed_use: str) -> dict[str, Any]:
    return _result("zoning_lookup_use", zoning_services.lookup_use_status(jurisdiction, zone_code, proposed_use))


def zoning_list_allowed_uses(
    jurisdiction: str,
    zone_code: str,
    status_filter: list[str] | None = None,
) -> dict[str, Any]:
    return _result("zoning_list_allowed_uses", zoning_services.list_allowed_uses(jurisdiction, zone_code, status_filter))


def zoning_search_code(jurisdiction: str, query: str, limit: int = 8) -> dict[str, Any]:
    return _result("zoning_search_code", zoning_services.search_zoning_code(jurisdiction, query, limit))


def zoning_get_standards(jurisdiction: str, zone_code: str) -> dict[str, Any]:
    return _result("zoning_get_standards", zoning_services.get_development_standards(jurisdiction, zone_code))


def zoning_get_overlays(parcel_id: str) -> dict[str, Any]:
    return _result("zoning_get_overlays", zoning_services.get_overlays_and_constraints(parcel_id))


def zoning_build_feasibility(parcel_id: str, proposed_use: str) -> dict[str, Any]:
    warnings = ["Screening context only; not a legal, permitting, engineering, or entitlement determination."]
    return _result(
        "zoning_build_feasibility",
        zoning_services.build_parcel_feasibility_report(parcel_id, proposed_use),
        warnings=warnings,
    )


def zoning_compare_zones(proposed_use: str, jurisdictions: list[str] | None = None) -> dict[str, Any]:
    return _result("zoning_compare_zones", zoning_services.compare_zones_for_use(proposed_use, jurisdictions))


HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    name: value
    for name, value in globals().copy().items()
    if callable(value) and name.startswith(("parcel_", "gis_", "context_", "zoning_"))
}
