from __future__ import annotations

from .contracts import ToolContract


def _contract(name: str, domain: str, description: str, *source_ids: str) -> ToolContract:
    return ToolContract(name=name, domain=domain, description=description, source_ids=tuple(source_ids))


TOOL_CONTRACTS = (
    _contract("parcel_get_summary", "parcel", "Get current live assessor details for one Skagit parcel.", "skagit_property_onestop"),
    _contract("parcel_get_history", "parcel", "Get live year-over-year assessment history for one parcel.", "skagit_property_onestop"),
    _contract("parcel_get_sales", "parcel", "Get live transfer and sale history for one parcel.", "skagit_property_onestop"),
    _contract("parcel_get_land", "parcel", "Get the live assessor land-segment breakdown for one parcel.", "skagit_property_onestop"),
    _contract("parcel_get_improvements", "parcel", "Get live building and improvement details for one parcel.", "skagit_property_onestop"),
    _contract("parcel_get_permits", "parcel", "Get live assessor-linked permit history for one parcel.", "skagit_property_onestop"),
    _contract("parcel_get_tax_detail", "parcel", "Get detailed live tax-statement data for one parcel and optional year.", "skagit_property_onestop"),
    _contract("parcel_get_full_report", "parcel", "Get a combined live parcel report with details, history, sales, land, and improvements.", "skagit_property_onestop"),
    _contract("gis_list_layers", "gis", "List registered GIS layers and bundles.", "openskagit_gis_registry"),
    _contract("gis_get_layer_metadata", "gis", "Get live ArcGIS metadata for a registered layer.", "openskagit_gis_registry"),
    _contract("gis_get_parcel", "gis", "Get the county GIS parcel feature and optional geometry.", "skagit_county_gis"),
    _contract("gis_get_overlays", "gis", "Query selected GIS overlays intersecting one parcel.", "skagit_county_gis", "state_federal_gis"),
    _contract("gis_query_layer", "gis", "Run a bounded read-only query against one registered ArcGIS layer.", "openskagit_gis_registry"),
    _contract(
        "context_get_census",
        "context",
        "Get Census ACS area-level context matched by a point on one parcel.",
        "openskagit_postgis",
        "us_census_geocoder",
        "us_census_acs5",
    ),
    _contract(
        "context_get_soils",
        "context",
        "Get NRCS SSURGO map units intersecting one parcel polygon.",
        "openskagit_postgis",
        "nrcs_soil_data_access",
    ),
    _contract("zoning_resolve_parcel", "zoning", "Resolve a parcel ID or address to jurisdiction and zoning context.", "openskagit_postgis", "openskagit_zoning_corpus"),
    _contract("zoning_get_profile", "zoning", "Get a structured profile for one jurisdiction and zone.", "openskagit_zoning_corpus"),
    _contract("zoning_lookup_use", "zoning", "Look up the status of a proposed use in one zone.", "openskagit_zoning_corpus"),
    _contract("zoning_list_allowed_uses", "zoning", "List structured allowed uses for one zone.", "openskagit_zoning_corpus"),
    _contract("zoning_search_code", "zoning", "Search imported zoning source text with citations.", "openskagit_zoning_corpus"),
    _contract("zoning_get_standards", "zoning", "Get structured development standards for one zone.", "openskagit_zoning_corpus"),
    _contract("zoning_get_overlays", "zoning", "Get zoning-related overlays and constraints for one parcel.", "openskagit_postgis", "skagit_county_gis"),
    _contract("zoning_build_feasibility", "zoning", "Build a cited screening report for a parcel and proposed use.", "openskagit_postgis", "openskagit_zoning_corpus", "skagit_county_gis"),
    _contract("zoning_compare_zones", "zoning", "Compare zones for a proposed use across optional jurisdictions.", "openskagit_zoning_corpus"),
)

TOOL_CONTRACT_BY_NAME = {contract.name: contract for contract in TOOL_CONTRACTS}
if len(TOOL_CONTRACT_BY_NAME) != len(TOOL_CONTRACTS):
    raise RuntimeError("Unified OpenSkagit tool names must be unique.")
if not all(contract.read_only for contract in TOOL_CONTRACTS):
    raise RuntimeError("The initial unified OpenSkagit catalog must be read-only.")


def get_tool_contract(name: str) -> ToolContract:
    try:
        return TOOL_CONTRACT_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"Unknown OpenSkagit tool: {name}") from exc
