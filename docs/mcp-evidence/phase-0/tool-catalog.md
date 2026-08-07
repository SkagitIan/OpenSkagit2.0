# Phase 0 Frozen MCP Tool Catalog

Freeze date: 2026-08-01  
Contract version: `1.0`  
Initial GA baseline: 31 existing read-only tools  
Target catalog: 45 read-only tools

The baseline below was generated from `openskagit_tools.registry.TOOL_CONTRACTS`,
not copied from a documentation table. Tests on the freeze date proved exact
registry, handler, FastMCP, and catalog parity.

## Frozen 31-tool baseline

| # | Tool | Domain | Registered source IDs |
| ---: | --- | --- | --- |
| 1 | `parcel_search` | parcel | `openskagit_postgis` |
| 2 | `parcel_get_summary` | parcel | `skagit_property_onestop` |
| 3 | `parcel_get_history` | parcel | `skagit_property_onestop` |
| 4 | `parcel_get_sales` | parcel | `skagit_property_onestop` |
| 5 | `parcel_get_land` | parcel | `skagit_property_onestop` |
| 6 | `parcel_get_improvements` | parcel | `skagit_property_onestop` |
| 7 | `parcel_get_permits` | parcel | `skagit_property_onestop` |
| 8 | `parcel_get_tax_detail` | parcel | `skagit_property_onestop` |
| 9 | `parcel_get_full_report` | parcel | `skagit_property_onestop` |
| 10 | `gis_list_layers` | GIS | `openskagit_gis_registry` |
| 11 | `gis_get_layer_metadata` | GIS | `openskagit_gis_registry` |
| 12 | `gis_get_parcel` | GIS | `skagit_county_gis` |
| 13 | `gis_get_overlays` | GIS | `skagit_county_gis`, `state_federal_gis` |
| 14 | `gis_query_layer` | GIS | `openskagit_gis_registry` |
| 15 | `context_get_census` | context | `openskagit_postgis`, `us_census_geocoder`, `us_census_acs5` |
| 16 | `context_get_soils` | context | `openskagit_postgis`, `nrcs_soil_data_access` |
| 17 | `zoning_resolve_parcel` | zoning | `openskagit_postgis`, `openskagit_zoning_corpus` |
| 18 | `zoning_get_profile` | zoning | `openskagit_zoning_corpus` |
| 19 | `zoning_lookup_use` | zoning | `openskagit_zoning_corpus` |
| 20 | `zoning_list_allowed_uses` | zoning | `openskagit_zoning_corpus` |
| 21 | `zoning_search_code` | zoning | `openskagit_zoning_corpus` |
| 22 | `zoning_get_standards` | zoning | `openskagit_zoning_corpus` |
| 23 | `zoning_get_overlays` | zoning | `openskagit_postgis`, `skagit_county_gis` |
| 24 | `zoning_build_feasibility` | zoning | `openskagit_postgis`, `openskagit_zoning_corpus`, `skagit_county_gis` |
| 25 | `zoning_compare_zones` | zoning | `openskagit_zoning_corpus` |
| 26 | `budget_list_jurisdictions` | budget | `local_budget_documents` |
| 27 | `budget_get_summary` | budget | `local_budget_documents` |
| 28 | `budget_get_breakdown` | budget | `local_budget_documents` |
| 29 | `budget_get_trend` | budget | `local_budget_documents` |
| 30 | `budget_compare_jurisdictions` | budget | `local_budget_documents` |
| 31 | `budget_search_documents` | budget | `local_budget_documents` |

All 31 names are frozen against accidental removal, rename, required-input
addition, or semantic change. “Frozen baseline” does not waive Phase 2-5 review;
it prevents silent contract drift while that evidence is built.

## Proposed 14-tool expansion

These names are target scope, not current public tools. They must not enter the
stable catalog until their owning phase gates pass.

| # | Tool | Domain owner | Admission dependency |
| ---: | --- | --- | --- |
| 32 | `data_list_sources` | `openskagit_tools` coordination | source registry/status/freshness policy |
| 33 | `data_get_source_status` | `openskagit_tools` coordination | source registry/status/freshness policy |
| 34 | `data_get_freshness` | `openskagit_tools` coordination | source registry/status/freshness policy |
| 35 | `data_get_latest_assessor_sync` | `assessor_sync` | sanitized read-only status service |
| 36 | `opportunity_list_screen_types` | `opportunity` | reviewed deterministic screen catalog |
| 37 | `opportunity_search` | `opportunity` | limits, explainability, privacy review |
| 38 | `opportunity_get_parcel_signals` | `opportunity` | approved public parcel facts only |
| 39 | `opportunity_explain_match` | `opportunity` | deterministic evidence/caveat contract |
| 40 | `tax_get_parcel_summary` | `taxtool` | tax-year and methodology contract |
| 41 | `tax_get_parcel_trend` | `taxtool` | bounded year coverage and methodology |
| 42 | `tax_get_levy_breakdown` | `taxtool` | year-qualified joins and labels |
| 43 | `tax_get_delinquency_status` | `tax_delinquency` | proven verification age and coverage |
| 44 | `land_ledger_get_parcel` | `land_ledger` | explicit city coverage and assumptions |
| 45 | `land_ledger_get_jurisdiction_summary` | `land_ledger` | explicit city coverage and assumptions |

## Baseline review flags

The following flags do not remove tools from the frozen catalog. They identify
where stable status needs explicit security, performance, privacy, freshness, or
semantic evidence before GA acceptance.

| Tool or group | Required review | Interim rule |
| --- | --- | --- |
| `gis_query_layer` | Caller-supplied `where`, field/operator allowlists, bounded expression complexity, registered URL enforcement, response/geometry limits, upstream amplification | Highest-risk existing contract; privatize or version if safe public semantics cannot be proven. |
| `parcel_search` | Returned-field privacy/sensitivity classification, hard query/row limits, indexed plans | Do not add owner/entity search semantics. |
| Eight live Property OneStop tools | Upstream timeout/rate policy, parser fixtures, source-change handling, public field classification | Preserve narrow parcel-ID contracts; no bulk traversal. |
| `parcel_get_full_report` | Fan-out deadline, partial-result semantics, maximum response bytes | Keep explicit partial warnings and bound every section. |
| `gis_get_parcel`, `gis_get_overlays`, `zoning_get_overlays` | Geometry precision/size, layer quotas, fan-out concurrency, partial results | Default to bounded geometry and registered layers only. |
| `context_get_census` | ACS release/effective date, area-level caveat, geocoder/fallback provenance | Never imply parcel-level demographic facts. |
| `context_get_soils` | NRCS timeout/schema/farmland-field checks, screening caveat | Never imply site-specific engineering determination. |
| Zoning profile/use/standard/search tools | Corpus verification date, jurisdiction coverage, citations, unknown handling | Screening information only; preserve source citations. |
| `zoning_build_feasibility` | Legal/entitlement language, composite timeout, missing evidence | Always return the existing non-determination warning. |
| `zoning_compare_zones` | Result-size and jurisdiction-count bounds, semantic comparability | Keep comparisons screening-only. |
| Budget list/summary/breakdown/trend/compare | Published/current/reviewed coverage, fiscal year, document status, aggregation limits | Use reviewed line items and identify missing coverage. |
| `budget_search_documents` | Text length, result count, page evidence, response size | Page-numbered evidence and hard search/result limits required. |

## Catalog drift found

- Runtime registry, current public page, and `docs/mcp-catalog.md` say 31.
- `docs/platform-catalog.md` still says 25 and omits the six budget tools from its
  implementation-status inventory.
- `docs/deployment-inventory-2026-07-16.md` accurately records the older 25-tool
  state for that date and should remain historical evidence, not be rewritten as
  a current inventory.

Phase 2 should generate the current catalog and snapshot from the registry and
make current-document drift a CI failure.
