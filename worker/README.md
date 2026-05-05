# Skagit Property Agent Worker

Cloudflare Worker that turns Skagit County public property pages plus ArcGIS overlays into an agent-ready parcel context packet.

## Run locally

```bash
npm install
npm run dev
```

## Deploy

```bash
npx wrangler login
npm run deploy
```

## Core endpoints

```txt
/openapi.json
/mcp
/api/search?q=320 orange
/api/property?parcel=P72063
/api/property?parcel=P72063&raw=1
/api/context?parcel=P72063
/api/tax-detail?parcel=P72063&year=2025
/api/census?parcel=P72063
/api/soils?parcel=P72063
```

Use `/openapi.json` as the Custom GPT Action schema URL after deployment. The schema treats
`/api/context` as the default full-context property research action.

Use `/mcp` as the remote MCP connector URL for Claude. The MCP server exposes read-only tools
for parcel search, full property context, property summary, GIS overlays, Census, soils, and
GIS layer discovery. To require a bearer token, set the `MCP_BEARER_TOKEN` Worker secret and
configure Claude with that token.

Property summaries include parsed value history, tax statement years, structured current/prior tax statements, transfers from the county Transfers/Sales page, comparable-sales data from the county PropertySales flow when available, and Census ACS 5-year block-group/tract/place/county context matched by parcel centroid.

## GIS endpoints

```txt
/api/gis/layers
/api/gis/metadata?layer=fema_flood
/api/gis/query?layer=zoning&where=1=1
/api/gis/parcel?parcel=P72063
/api/gis/parcel-overlays?parcel=P72063
/api/gis/parcel-overlays?parcel=P72063&bundles=core
/api/gis/parcel-overlays?parcel=P72063&bundles=development
/api/gis/parcel-overlays?parcel=P72063&bundles=utilities_services
/api/gis/parcel-overlays?parcel=P72063&bundles=state_federal
/api/gis/parcel-overlays?parcel=P72063&bundles=core,development,utilities_services,state_federal
```

## Bundles

Default `/api/context` and `/api/gis/parcel-overlays` now run all bundles:

```txt
core
  zoning, uga, npdes, wria, watershed_basin, surface_water_limited_stream,
  stream_buffer, wellhead_protection, big_lake_water_mitigation

development
  alluvial_fans, slope_stability, landslide_areas, aerial_interpreted_wetlands,
  skagit_wetlands, hydric_soils, fema_bfe, fema_floodway, fema_flood,
  fema_panels, landfill_influence

utilities_services
  fire_district, school_district, sewer_district, dike_district,
  drainage_district, road_maintenance_district, group_a_water_systems,
  group_a_b_wells

state_federal
  mtca_cleanup_sites, ust_facilities, wdfw_priority_habitats,
  fema_nfhl_zones, fema_nfhl_panels, dnr_natural_heritage_current,
  dnr_managed_lands, tribal_lands, forest_practices, epa_superfund
```

Overlay calls are executed concurrently with `Promise.all`.
