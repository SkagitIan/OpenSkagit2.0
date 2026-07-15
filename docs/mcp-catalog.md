# OpenSkagit MCP Catalog

> Current compatibility catalog: this document describes the existing Cloudflare Worker MCP contract. The cross-project inventory, target ownership, and consolidation decisions are documented in [the platform catalog](platform-catalog.md), [the consolidation plan](platform-consolidation-plan.md), and [the deprecation register](deprecation-register.md).

## Canonical Unified MCP

Public catalog and access request:

```text
https://openskagit.com/mcp/
```

Remote MCP endpoint for Claude and other compatible clients:

```text
https://openskagit.com/mcp/api/
```

The endpoint publishes 22 read-only parcel, GIS, and zoning tools from the versioned `openskagit_tools` registry. It uses Streamable HTTP, OAuth authorization-code flow with PKCE, approved client credentials, the `openskagit.read` scope, revocable grants, and encrypted client-secret storage. The catalog page is generated from the same registry used for MCP discovery.

Access requests are reviewed in Django admin. Issue an approved Claude-compatible client with:

```powershell
python manage.py approve_mcp_access REQUEST_ID --name "Claude connector"
```

The command displays the client secret once. Keep `SECRET_KEY` stable because it protects stored OAuth client credentials. The public form never issues or displays a credential. See [MCP access operations](mcp-access-operations.md) for review, delivery, revocation, incident, and smoke-test procedures.

For local development, the `.mcp.json` entry named `openskagit` starts the same registry over stdio. The older `assessor-mcp`, `gis-mcp`, and `zoning-mcp` entries remain temporarily as compatibility bridges. All unified results use the common `data`, `sources`, `freshness`, `warnings`, and `errors` envelope.

### Standalone bearer deployment (fallback only)

`railway.unified-mcp.json` remains available for an isolated fallback service using a static bearer token. It is not the canonical OpenSkagit.com connector. The canonical endpoint is served by the Django ASGI deployment so the catalog, approval records, OAuth provider, and MCP tools share one reviewed control plane.

### Legacy Cloudflare compatibility

The older Cloudflare Worker endpoint remains a compatibility dependency for existing Ask Agent behavior while its unique Census/soils capabilities and consumers are migrated. It is not the URL for new external connectors.


## Relationship To Existing Tools

The agent has two classes of tools:

- Local DuckDB function tools: `get_analysis_context` and `run_analysis_query`.
- Remote MCP-backed tools: live Cloudflare Worker tools backed by county property pages, ArcGIS REST services, Census context, and soils services.

Use DuckDB for broad tabular analysis:

- Cohort rollups across many parcels.
- Sales ratio checks.
- Median/average sale price summaries.
- Assessor table joins.
- Regression-style aggregate analysis.
- Questions that depend on the imported Postgres/DuckDB dataset.

Use MCP for live parcel and geospatial context:

- Address-to-parcel lookup.
- One-parcel property dossiers.
- Zoning and critical-area overlays.
- Flood, wetland, slope, landslide, water, sewer, school, fire, dike, drainage, and road district context.
- Census area estimates matched by parcel centroid.
- NRCS SSURGO soils context.
- ArcGIS layer discovery and metadata.

The tools are complementary. A typical parcel answer may use DuckDB for local comparable sales and MCP for parcel-specific overlays.

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENSKAGIT_ENABLE_MCP` | `true` | Set to `false` to disable the remote MCP server. |
| `OPENSKAGIT_MCP_URL` | Cloudflare Worker `/mcp` URL | Streamable HTTP MCP endpoint. |
| `OPENSKAGIT_MCP_BEARER_TOKEN` | empty | Optional bearer token. Must match the Worker `MCP_BEARER_TOKEN` secret if that secret is set. |
| `OPENSKAGIT_MCP_TIMEOUT_SECONDS` | `15` | HTTP request timeout for MCP calls. |
| `OPENSKAGIT_MCP_SSE_READ_TIMEOUT_SECONDS` | `60` | Stream/read timeout for MCP transport. |

The Worker currently supports unauthenticated access unless `MCP_BEARER_TOKEN` is configured on the Worker.

## MCP Transport And Bridge

The Worker implements JSON-RPC MCP over HTTP at `/mcp`.

Discovery request:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

Tool call request shape:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_gis_overlays",
    "arguments": {
      "parcel": "P96023",
      "bundles": "core,development"
    }
  }
}
```

In this Django app, `core.agent._call_openskagit_mcp_tool()` sends these JSON-RPC messages. Each MCP catalog entry is exposed to the model as a typed function tool with the same name, and that function tool delegates to the remote MCP server.

This bridge exists because the deployed Worker currently returns ordinary JSON-RPC HTTP responses and does not maintain the streaming session expected by the Agents SDK's built-in streamable HTTP MCP client.

## Tool Catalog

### `search_parcels`

Search Skagit County parcels by address text or parcel number.

Inputs:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `q` | string | yes | Address text or parcel number, for example `813 Cultus Mountain` or `P96023`. |

Use when:

- The user gives an address instead of a parcel number.
- The user gives a partial or uncertain parcel identifier.
- A later tool requires a normalized `P...` parcel ID.

Returns:

- Query text.
- Count.
- Candidate results with label, parcel ID, latitude, longitude, city, and ZIP when available.

Agent guidance:

- Use this before parcel-specific tools when the user gives an address.
- If there are multiple plausible matches, state that and ask the user to choose or use the most exact match only when the request is unambiguous.

### `get_property_context`

Get the default full-context property research packet for one parcel.

Inputs:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `parcel` | string | yes | Parcel ID such as `P96023`. |
| `raw` | boolean | no | Include raw county page payloads. Default `false`. |
| `bundles` | string | no | Comma-separated GIS bundles. Defaults to all bundles. |
| `layers` | string | no | Comma-separated explicit GIS layer keys. |

Use when:

- The user asks a broad parcel-specific question.
- The user needs a property research packet combining assessor/property context with GIS overlays.
- The request mentions parcel development constraints, taxes, ownership, valuation history, transfers, or environmental/service overlays.

Returns:

- Top-level parcel ID.
- Property summary/dossier.
- GIS overlay results.
- Token/character estimate metadata.

Agent guidance:

- This can be large. Prefer narrower tools if the user asks only for soils, census, or GIS overlays.
- Do not request `raw=true` unless raw county payloads are specifically needed.

### `get_property_summary`

Get parsed assessor/property context for one parcel without GIS overlays.

Inputs:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `parcel` | string | yes | Parcel ID such as `P96023`. |
| `raw` | boolean | no | Include raw county page payloads. Default `false`. |

Use when:

- The user wants parcel facts, value history, tax context, transfers, comps, or assessor details.
- GIS overlays are not needed.
- You need a smaller response than `get_property_context`.

Returns:

- Parsed property details.
- Taxes and value history where available.
- Transfers/sales and related parcel context where available.
- Census context and agent flags where available.

Agent guidance:

- Pair this with DuckDB for local comparable-sale analysis if the answer needs broader market context.

### `get_gis_overlays`

Get GIS overlays intersecting a parcel.

Inputs:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `parcel` | string | yes | Parcel ID such as `P96023`. |
| `bundles` | string | no | Comma-separated bundles: `core`, `development`, `utilities_services`, `state_federal`. |
| `layers` | string | no | Comma-separated explicit layer keys. |

Use when:

- The user asks about zoning, critical areas, flood context, wetlands, utilities, districts, water systems, public lands, cleanup sites, or development constraints.
- The answer needs ArcGIS overlay facts for a single parcel.

Returns:

- Parcel geometry summary.
- Selected overlay layers.
- Intersecting features and layer status.

Agent guidance:

- Prefer `bundles` for broad categories.
- Prefer `layers` when the user asks for a specific overlay.
- Explain that overlays are GIS screening context, not a final permit/legal determination.

### `get_census_context`

Get Census ACS area-level context matched by parcel centroid.

Inputs:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `parcel` | string | yes | Parcel ID such as `P96023`. |

Use when:

- The user asks about surrounding demographic, economic, household, or area-level context.
- The answer needs Census geographies around a parcel.

Returns:

- Census geography matches.
- ACS 5-year area estimates where available.

Agent guidance:

- Always state that Census values are area-level estimates matched by parcel centroid, not parcel-level facts.

### `get_soils_context`

Get NRCS SSURGO soil map units intersecting a parcel polygon.

Inputs:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `parcel` | string | yes | Parcel ID such as `P96023`. |

Use when:

- The user asks about soils, drainage, flooding frequency, farmland classification, hydrologic group, or development suitability.

Returns:

- Intersecting soil map units.
- Drainage, flood frequency, hydrologic group, and farmland class where available.

Agent guidance:

- Treat as screening context.
- Avoid engineering, septic, or permit conclusions without stating limitations.

### `list_gis_layers`

List available GIS overlay bundles and layer keys.

Inputs:

No arguments.

Use when:

- The agent needs to discover valid bundle names or layer keys.
- The user asks what GIS layers are available.
- A specific requested layer name needs to be mapped to an available key.

Returns:

- Default bundles.
- Bundle-to-layer mappings.
- Layer keys, labels, source URLs, configured output fields, and notes.

## GIS Bundles

### `core`

General parcel planning and water-resource context:

- `zoning`
- `uga`
- `npdes`
- `wria`
- `watershed_basin`
- `surface_water_limited_stream`
- `stream_buffer`
- `wellhead_protection`
- `big_lake_water_mitigation`

### `development`

Development constraint and hazard context:

- `alluvial_fans`
- `slope_stability`
- `landslide_areas`
- `aerial_interpreted_wetlands`
- `skagit_wetlands`
- `hydric_soils`
- `fema_bfe`
- `fema_floodway`
- `fema_flood`
- `fema_panels`
- `landfill_influence`

### `utilities_services`

Service and assessment district context:

- `fire_district`
- `school_district`
- `sewer_district`
- `dike_district`
- `drainage_district`
- `road_maintenance_district`
- `group_a_water_systems`
- `group_a_b_wells`

### `state_federal`

State and federal environmental/public-land context:

- `mtca_cleanup_sites`
- `ust_facilities`
- `wdfw_priority_habitats`
- `fema_nfhl_zones`
- `fema_nfhl_panels`
- `dnr_natural_heritage_current`
- `dnr_managed_lands`
- `tribal_lands`
- `forest_practices`
- `epa_superfund`

## Agent Decision Rules

Use this order for parcel-specific questions:

1. If the user gives an address, call `search_parcels`.
2. If the user asks for broad parcel context, call `get_property_context`.
3. If the user asks only for assessor/tax/value/property details, call `get_property_summary`.
4. If the user asks only about overlays or constraints, call `get_gis_overlays`.
5. If the user asks specifically about demographics, call `get_census_context`.
6. If the user asks specifically about soils, call `get_soils_context`.
7. Use DuckDB after MCP when the answer needs broader cohort comparisons.

Use this order for countywide or market questions:

1. Call `get_analysis_context`.
2. Use `run_analysis_query` against DuckDB/Postgres-derived tables.
3. Use MCP only if the question requires live parcel/GIS context that is not present in the tabular dataset.

## Safety And Reliability Notes

- MCP tools are read-only.
- Keep MCP responses scoped. Prefer specific layer/bundle calls over full context when possible.
- Do not treat reval area as neighborhood.
- Do not present GIS overlays as final legal, permitting, engineering, environmental, or appraisal determinations.
- State data-source limitations for Census, soils, and ArcGIS overlays.
- If the MCP server is unavailable, set `OPENSKAGIT_ENABLE_MCP=false` to keep DuckDB-only analysis running.
