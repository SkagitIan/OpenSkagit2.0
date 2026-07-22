from __future__ import annotations

from typing import Any

from . import services


def build_opportunity_tools():
    """Build the parcel-screening function-tools, for reuse by any OpenAI Agents SDK agent
    (e.g. ask_agent) that needs investment-opportunity screening alongside its other tools.

    These wrap the plain scoring/filter functions in opportunity/services.py directly --
    not opportunity/ai_search.py, which is a separate saved-search orchestration layer with
    its own persistence, background-worker, and results-page UI."""
    from agents import function_tool

    @function_tool
    def screen_delinquent_tax_pressure(
        min_years: int = 0,
        min_due: float = 0,
        min_land_ratio: float = 0,
        improved: str = "",
        place: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Screen parcels with delinquent property tax pressure, scored by years delinquent, amount due, and land-to-building value ratio. improved: 'vacant', 'improved', or '' for either. place: 'city', 'unincorporated', or '' for either."""
        filters = {
            "min_years": str(min_years),
            "min_due": str(min_due),
            "min_land_ratio": str(min_land_ratio),
            "improved": improved,
            "place": place,
        }
        return {"rows": services.delinquent_tax_pressure(filters, min(max(limit, 1), 50))}

    @function_tool
    def screen_vacant_buildable_lots(min_acres: float = 0.10, max_building: float = 10000, limit: int = 20) -> dict[str, Any]:
        """Screen vacant or near-vacant buildable lots in residential-eligible zones, scored by size, utilities, and zoning fit."""
        filters = {"min_acres": str(min_acres), "max_building": str(max_building)}
        return {"rows": services.vacant_buildable_lots(filters, min(max(limit, 1), 50))}

    @function_tool
    def screen_possible_lot_splits(min_acres: float = 0.35, max_building: float = 250000, limit: int = 20) -> dict[str, Any]:
        """Screen parcels significantly larger than their zoning/place cohort's median lot size -- possible short-plat/lot-split candidates."""
        filters = {"min_acres": str(min_acres), "max_building": str(max_building)}
        return {"rows": services.possible_lot_splits(filters, min(max(limit, 1), 50))}

    @function_tool
    def screen_teardown_candidates(min_land_value: float = 150000, max_building: float = 180000, limit: int = 20) -> dict[str, Any]:
        """Screen improved parcels where land value substantially exceeds building value and the building is older/lower-condition -- possible teardown-and-rebuild candidates."""
        filters = {"min_land_value": str(min_land_value), "max_building": str(max_building)}
        return {"rows": services.teardown_candidates(filters, min(max(limit, 1), 50))}

    @function_tool
    def screen_assemblage_opportunities(min_cluster: int = 2, limit: int = 20) -> dict[str, Any]:
        """Screen clusters of adjacent, commonly-owned parcels that could be assembled into a larger development site. min_cluster is the minimum number of parcels in the cluster."""
        filters = {"min_cluster": str(min_cluster)}
        return {"rows": services.assemblage_opportunities(filters, min(max(limit, 1), 50))}

    return [
        screen_delinquent_tax_pressure,
        screen_vacant_buildable_lots,
        screen_possible_lot_splits,
        screen_teardown_candidates,
        screen_assemblage_opportunities,
    ]
