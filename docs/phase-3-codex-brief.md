# Phase 3 Codex Brief
## Civic Intelligence Platform — WA State + Federal GIS

**Builds on:** Phase 2 verified and passing. 17 tests passing, 2 skipped.

**Goal:** Add Washington State and federal GIS sources to the source catalog so the agent can answer questions about critical areas, water rights, wetlands, federal land, and topography — without writing a single new adapter.

**Exit criteria:** `POST /ask` with `"Are there wetlands on parcel P48165?"` correctly routes to WA Ecology live and returns critical area or wetland overlay data with a confidence score and cited source.

---

## What changes in Phase 3

```
New catalog seeds only
  catalog/seeds/wa_state.yaml      ← WA DNR, Ecology, DOT, WDFW, SOS
  catalog/seeds/federal_gis.yaml   ← USGS, BLM, USFS

Planner update
  agent/planner.py                 ← new domains, state/federal routing guidance

New tests
  agent/tests/fixtures/p48165_wetlands_expected.json
  agent/tests/test_golden.py       ← new live fixture test

No new Workers. No new Python adapter files.
```

FEMA NFHL is already in the catalog from Phase 2. Do not re-add it.

---

## Coordinate System Rule

Phase 2 required `in_sr: 102748` (Washington State Plane North, EPSG:2926) for the Skagit zoning service. This will not be universal.

Before writing config for each source, verify its spatial reference. The pattern:

```
GET {base_url}?f=json
```

Look for `"spatialReference"` in the response. Common values for WA State sources:

```
102748 or 2926  — WA State Plane North (most county/state services)
102100 or 3857  — Web Mercator (common for federal services)
4326            — WGS84 lat/lon (less common for cadastral data)
```

Set `in_sr` in the source config to whatever the service reports. If a geometry-based query fails with a spatial reference error, this is why.

---

## Ticket 1 — WA State Source Discovery + Catalog

**File:** `catalog/seeds/wa_state.yaml`

For each source below, fetch the service root (`?f=json`) to verify it is reachable and to confirm the spatial reference and available layers before writing the config. If a service root is unreachable, mark it `status: "needs_verification"` and continue.

### WA DNR

```yaml
sources:
  wa_dnr_ownership:
    name: "WA DNR Land Ownership"
    type: arcgis_rest
    base_url: "https://gis.dnr.wa.gov/site3/rest/services/Public_Boundaries/WADNR_PUBLIC_Cadastre_OpenData/MapServer"
    domains:
      - land_ownership
      - state_land
      - dnr
    supports:
      - query_by_geometry
      - query_by_attribute
    config:
      layer_id: 11          # verify — Public Land Survey ownership layer
      in_sr: 102748
      owner_field: "OWNERNM"
      note: "Verify layer_id at service root before use"

  wa_dnr_forest:
    name: "WA DNR Forest Practices"
    type: arcgis_rest
    base_url: "https://gis.dnr.wa.gov/site3/rest/services/Forest_Practices/WADNR_PUBLIC_FP_OpenData/MapServer"
    domains:
      - forest
      - timber
      - forest_practices
    supports:
      - query_by_geometry
    config:
      layer_id: 0
      in_sr: 102748
      note: "Verify layer_id at service root before use"
```

### WA Ecology

```yaml
  wa_ecology_wetlands:
    name: "WA Ecology Wetlands"
    type: arcgis_rest
    base_url: "https://fortress.wa.gov/ecy/gispublic/rest/services/Wetlands/WADOE_ECY_Wetlands/MapServer"
    domains:
      - wetlands
      - critical_areas
      - ecology
    supports:
      - query_by_geometry
    config:
      layer_id: 0
      in_sr: 102748
      wetland_type_field: "WETLAND_TYPE"
      note: "Primary source for wetland critical area questions. Verify layer_id."

  wa_ecology_water_rights:
    name: "WA Ecology Water Rights"
    type: arcgis_rest
    base_url: "https://fortress.wa.gov/ecy/gispublic/rest/services/WR/WADOE_ECY_WaterRights/MapServer"
    domains:
      - water_rights
      - water
      - ecology
    supports:
      - query_by_geometry
      - query_by_attribute
    config:
      layer_id: 0
      in_sr: 102748
      note: "Water rights by location. Verify layer_id."
```

### WA DOT

```yaml
  wa_dot_roads:
    name: "WA DOT State Roads"
    type: arcgis_rest
    base_url: "https://data.wsdot.wa.gov/arcgis/rest/services/Shared/CountyBoundaries/MapServer"
    domains:
      - roads
      - access
      - transportation
    supports:
      - query_by_geometry
      - query_by_attribute
    config:
      layer_id: 0
      in_sr: 4326
      note: "For road access questions. WSDOT typically uses 4326. Verify."
```

### WA DFW

```yaml
  wa_dfw_habitat:
    name: "WA DFW Priority Habitats"
    type: arcgis_rest
    base_url: "https://fortress.wa.gov/dfw/public/publicwdfw/rest/services/PHS/WDFW_PHS/MapServer"
    domains:
      - wildlife_habitat
      - critical_areas
      - fish_wildlife
    supports:
      - query_by_geometry
    config:
      layer_id: 0
      in_sr: 102748
      habitat_field: "HABITAT_TYPE"
      note: "Priority Habitats and Species. Verify layer_id."
```

### WA Secretary of State

The Secretary of State business registry is not an ArcGIS service. It is a web search interface. Add it as a `web` type source for Phase 4 manual configuration. Do not attempt to configure it now.

```yaml
  wa_sos_business:
    name: "WA Secretary of State Business Search"
    type: web
    base_url: "https://ccfs.sos.wa.gov"
    domains:
      - business
      - corporations
      - llc
      - registered_agents
    supports:
      - query_by_name
      - query_by_ubi
    status: "needs_manual_config"
    config:
      endpoint: ""
      note: "Web form search. Requires manual endpoint discovery."
```

---

## Ticket 2 — Federal GIS Source Discovery + Catalog

**File:** `catalog/seeds/federal_gis.yaml`

Same verification pattern: fetch `{base_url}?f=json` before writing layer_id into config.

### USGS

```yaml
sources:
  federal_usgs_elevation:
    name: "USGS National Elevation Dataset"
    type: arcgis_rest
    base_url: "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
    domains:
      - topography
      - elevation
      - geology
    supports:
      - query_by_geometry
    config:
      layer_id: 0
      in_sr: 4326
      note: "ImageServer not MapServer — query pattern differs. Returns elevation values not features."

  federal_usgs_geology:
    name: "USGS Geologic Map"
    type: arcgis_rest
    base_url: "https://mrdata.usgs.gov/services/geo-us-2014/MapServer"
    domains:
      - geology
      - soils
      - lithology
    supports:
      - query_by_geometry
    config:
      layer_id: 0
      in_sr: 4326
      note: "Verify layer availability. USGS services occasionally reorganize."
```

### BLM

```yaml
  federal_blm_land:
    name: "BLM Federal Land Status"
    type: arcgis_rest
    base_url: "https://gis.blm.gov/arcgis/rest/services/lands_and_realty/BLM_Natl_SMA_Grazing_Allotments/MapServer"
    domains:
      - federal_land
      - blm
      - grazing
    supports:
      - query_by_geometry
    config:
      layer_id: 1
      in_sr: 4326
      admin_state_field: "ADMINST"
      note: "For federal land adjacency questions. Verify endpoint still active."

  federal_blm_surface:
    name: "BLM Surface Management Agency"
    type: arcgis_rest
    base_url: "https://gis.blm.gov/arcgis/rest/services/lands_and_realty/BLM_Natl_SMA_Surface_Management_Agency/MapServer"
    domains:
      - federal_land
      - land_ownership
      - land_management
    supports:
      - query_by_geometry
    config:
      layer_id: 1
      in_sr: 4326
      agency_field: "AGBUR"
```

### USFS

```yaml
  federal_usfs_boundaries:
    name: "USFS National Forest Boundaries"
    type: arcgis_rest
    base_url: "https://apps.fs.usda.gov/arcgis/rest/services/EDW/EDW_ForestSystemBoundaries_01/MapServer"
    domains:
      - federal_land
      - forest
      - usfs
    supports:
      - query_by_geometry
    config:
      layer_id: 1
      in_sr: 4326
      forest_name_field: "FORESTNAME"
      note: "Returns national forest name if parcel is within or adjacent."
```

---

## Ticket 3 — Seed Script Update

**File:** `catalog/seeds/seed.py` (modify existing)

Add `wa_state.yaml` and `federal_gis.yaml` to the list of files the seed script processes. The seed script is already idempotent — no other changes needed.

Verify the new sources appear in the catalog after reseeding:

```bash
python catalog/seeds/seed.py --env local
sqlite3 catalog/local.db "SELECT id, name, type FROM sources ORDER BY id;"
```

Expected: all existing Phase 1/2 sources plus the new WA state and federal GIS entries.

---

## Ticket 4 — Planner Update

**File:** `agent/planner.py` (modify existing)

Update `PLANNER_SYSTEM` in two places only.

**1. Extend the available domains list:**

```
# Add to existing domains list:
land_ownership, state_land, dnr, forest, forest_practices,
wetlands, critical_areas, ecology, water_rights, water,
roads, access, transportation, wildlife_habitat, fish_wildlife,
topography, elevation, geology, federal_land, blm, usfs,
business, corporations
```

**2. Add routing guidance after the existing investment/development guidance:**

```
For environmental or development feasibility questions, include:
wetlands, critical_areas, and water_rights steps from WA Ecology.

For questions about land near forests or federal land, include:
federal_land steps from BLM or USFS.

For questions about wildlife, habitat, or critical areas, include:
wildlife_habitat from WA DFW.

For topography or elevation questions, include: elevation from USGS.

For state land ownership questions, include: land_ownership from WA DNR.

Prefer state sources (wa_ecology_wetlands) over county sources 
(skagit_flood) when the domain overlaps — state sources have broader
geographic coverage.
```

No other changes to planner.py.

---

## Ticket 5 — ArcGIS Adapter: ImageServer Support

**File:** `workers/arcgis-adapter/src/index.ts` (minor modification)

USGS elevation uses an ImageServer, not a MapServer. The query URL pattern is the same but ImageServer returns pixel values, not feature records. Add a `server_type` field to the request interface and handle it:

```typescript
interface ArcGISRequest {
  base_url: string;
  layer_id: number;
  query_type: "by_attribute" | "by_geometry" | "by_parcel";
  server_type?: "MapServer" | "ImageServer";  // new, default "MapServer"
  params: { ... };  // unchanged
}
```

For `server_type: "ImageServer"`, use the `/identify` endpoint instead of `/query`:

```
{base_url}/identify?geometry={geometry}&geometryType=esriGeometryPoint&f=json
```

Return the result under `features: [{ attributes: { value: <pixel_value> } }]` to keep the response shape consistent with MapServer responses.

If `server_type` is omitted, default to `"MapServer"` behavior. This is a backward-compatible change.

---

## Ticket 6 — Golden Fixture: Wetlands Query

**File:** `agent/tests/fixtures/p48165_wetlands_expected.json`

```json
{
  "question": "Are there wetlands on parcel P48165?",
  "entity": "P48165",
  "required_sources": ["skagit_parcels"],
  "preferred_sources": ["wa_ecology_wetlands"],
  "min_evidence_count": 1,
  "confidence_min": "low",
  "answer_must_contain": ["P48165"],
  "answer_must_not_contain": ["I don't know", "unable to"],
  "missing_domains_acceptable": [
    "wetlands",
    "critical_areas",
    "water_rights",
    "wildlife_habitat"
  ],
  "note": "WA Ecology wetlands layer may return zero features if no mapped wetlands intersect the parcel. A zero-feature result is a valid answer (no mapped wetlands found) — not a failure."
}
```

Add a live golden test behind `RUN_LIVE_GOLDEN=1` that validates the response against this fixture. Note the `note` field: zero wetland features returned is a valid and correct answer — the test must not fail on an empty wetlands result.

---

## Ticket 7 — Source Verification Script

**File:** `catalog/tools/verify_sources.py`

Write a standalone script that pings each active source in the catalog and reports its status. This is a maintenance tool, not part of the agent.

```python
# Usage: python catalog/tools/verify_sources.py
# Output: table of source_id | reachable | spatial_ref | layer_count

import asyncio
import httpx
import sqlite3
import json
import os

DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")

async def check_source(source: dict) -> dict:
    """
    GET {base_url}?f=json and return:
    { id, name, reachable, spatial_ref, layer_count, error }
    """
    ...

async def main():
    # Load all active sources
    # Run check_source() concurrently with asyncio.gather
    # Print formatted table
    ...

if __name__ == "__main__":
    asyncio.run(main())
```

This script is what you run after adding new sources to confirm they are reachable and to verify the spatial reference matches what is in the config. It saves time compared to checking each URL manually.

---

## Running Order for Codex

```
1. Source discovery — fetch service roots for all new sources,
   record spatial references and layer IDs

2. catalog/seeds/wa_state.yaml — write with verified values

3. catalog/seeds/federal_gis.yaml — write with verified values

4. catalog/seeds/seed.py — add new files to seed list, reseed

5. workers/arcgis-adapter/src/index.ts — add ImageServer support

6. agent/planner.py — add new domains and routing guidance

7. catalog/tools/verify_sources.py — write verification script,
   run it, confirm all new sources are reachable

8. agent/tests/fixtures/p48165_wetlands_expected.json — write fixture

9. agent/tests/test_golden.py — add wetlands live test
```

---

## What to do when a source URL is wrong or moved

Federal and state GIS services reorganize endpoints without notice. If a fetch to a service root returns 404 or a non-JSON response:

1. Try appending `/MapServer?f=json` then `/FeatureServer?f=json` to the base URL
2. Search `{agency} arcgis rest services` to find the current catalog
3. If the correct URL cannot be found in 10 minutes, mark `status: "needs_verification"` and move on
4. Log the unverified sources in `README.md` under a new section: `## Sources Pending Verification`

Do not fabricate layer IDs or spatial references for sources you cannot reach. A source with `status: "needs_verification"` is handled gracefully by the dispatcher — it returns a structured error, not a crash.

---

## Definition of Done — Phase 3

- [ ] `pytest agent/tests/ -v` passes with zero failures
- [ ] All Phase 1 and Phase 2 tests still pass
- [ ] `python catalog/seeds/seed.py --env local` completes without error
- [ ] `sqlite3 catalog/local.db "SELECT count(*) FROM sources WHERE active=1;"` returns 12 or more
- [ ] `python catalog/tools/verify_sources.py` runs and outputs a status table
- [ ] At least 6 new sources show as reachable in the verification table
- [ ] `POST /ask` with `"Are there wetlands on P48165?"` routes to WA Ecology (or returns a reasoned answer if zero wetlands are mapped there)
- [ ] `POST /ask` with `"Is P48165 near federal land?"` includes a BLM or USFS step in its evidence
- [ ] arcgis_adapter Worker handles `server_type: "ImageServer"` without error
- [ ] `RUN_LIVE_GOLDEN=1 pytest agent/tests/test_golden.py -v` passes for wetlands fixture
- [ ] All unverified sources are listed in `README.md` under `## Sources Pending Verification`
- [ ] No new Workers were written
- [ ] No new Python adapter files were written
