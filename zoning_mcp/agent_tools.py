from __future__ import annotations

from typing import Any

from . import services


def build_zoning_tools():
    """Build the zoning function-tools, for reuse by any OpenAI Agents SDK agent
    (e.g. ask_agent) that needs zoning/feasibility screening alongside its other tools."""
    from agents import function_tool

    @function_tool
    def zoning_resolve_parcel(parcel_id: str | None = None, address: str | None = None) -> dict[str, Any]:
        """Resolve a parcel number or address to its jurisdiction and zoning code. Call this before other zoning tools when the user gives an address."""
        return services.resolve_parcel(parcel_id=parcel_id, address=address)

    @function_tool
    def zoning_get_profile(jurisdiction: str, zone_code: str) -> dict[str, Any]:
        """Get a zone's purpose/description and source chapter for one jurisdiction."""
        return services.get_zone_profile(jurisdiction, zone_code)

    @function_tool
    def zoning_lookup_use(jurisdiction: str, zone_code: str, proposed_use: str) -> dict[str, Any]:
        """Look up whether a proposed use (e.g. 'duplex', 'auto repair shop') is permitted, conditional, or prohibited in a zone."""
        return services.lookup_use_status(jurisdiction, zone_code, proposed_use)

    @function_tool
    def zoning_list_allowed_uses(jurisdiction: str, zone_code: str, status_filter: list[str] | None = None) -> dict[str, Any]:
        """List uses allowed in a zone, optionally filtered to specific status codes (P, AC, AD, HE, C, CUP)."""
        return services.list_allowed_uses(jurisdiction, zone_code, status_filter)

    @function_tool
    def zoning_search_code(jurisdiction: str, query: str, limit: int = 8) -> dict[str, Any]:
        """Full-text search a jurisdiction's imported zoning code sections for source-text evidence."""
        return services.search_zoning_code(jurisdiction, query, limit)

    @function_tool
    def zoning_get_standards(jurisdiction: str, zone_code: str) -> dict[str, Any]:
        """Get dimensional development standards (setbacks, height, lot size, density, coverage) for a zone."""
        return services.get_development_standards(jurisdiction, zone_code)

    @function_tool
    def zoning_get_overlays(parcel_id: str) -> dict[str, Any]:
        """Get zoning overlaps and known overlay/constraint notes for a specific parcel."""
        return services.get_overlays_and_constraints(parcel_id)

    @function_tool
    def zoning_build_feasibility(parcel_id: str, proposed_use: str) -> dict[str, Any]:
        """Build a full feasibility screen for a proposed use on a specific parcel: zone profile, use status, development standards, overlays, and citations. Screening context only, not a legal or permitting determination."""
        return services.build_parcel_feasibility_report(parcel_id, proposed_use)

    @function_tool
    def zoning_compare_zones(proposed_use: str, jurisdictions: list[str] | None = None) -> dict[str, Any]:
        """Compare which zones (optionally limited to specific jurisdictions) allow a proposed use."""
        return services.compare_zones_for_use(proposed_use, jurisdictions)

    return [
        zoning_resolve_parcel,
        zoning_get_profile,
        zoning_lookup_use,
        zoning_list_allowed_uses,
        zoning_search_code,
        zoning_get_standards,
        zoning_get_overlays,
        zoning_build_feasibility,
        zoning_compare_zones,
    ]
