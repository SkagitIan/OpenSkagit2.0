# Codex Prompt — Civic Intelligence Platform Phase 3

---

Phase 2 is complete and verified. You are building Phase 3 on top of it.

**Do not modify any Phase 1 or Phase 2 file unless the brief explicitly says to.** All 17 existing tests must continue passing.

Read `phase-3-codex-brief.md` completely before writing any code.

## What Phase 3 does

Extends the source catalog with Washington State GIS and federal GIS sources. Almost no new code — almost entirely YAML catalog entries, a planner update, a minor Worker addition for USGS ImageServer support, and a verification script.

**No new Workers. No new Python adapter files.** The arcgis_adapter already handles everything these sources speak.

## The one code change

The arcgis_adapter Worker needs a minor `server_type` addition for USGS elevation (ImageServer). This is backward-compatible and described in full in the brief. Everything else is catalog configuration.

## Hard rules — all carry forward

1. Frontend uses `fetch()` only.
2. Only `agent/model.py` calls the Anthropic API.
3. No civic data stored in D1.
4. Workers return structured errors, never crash.
5. Python adapters call Workers, not external APIs directly (except federal.py).
6. Concurrent steps use `asyncio.gather(..., return_exceptions=True)`.

## Phase 3 specific rules

7. **Verify before writing.** For every new source, fetch `{base_url}?f=json` and confirm it is reachable before writing its `layer_id` and `in_sr` into the YAML. If a service is unreachable, mark it `status: "needs_verification"` — do not guess or fabricate values.

8. **Spatial reference must match the service.** Phase 2 required `in_sr: 102748` for Skagit zoning. WA state services typically use `102748`. Federal services typically use `4326` or `102100`. Always check — do not assume.

9. **Zero features is a valid result.** If a wetlands query returns zero features over a parcel, that means no mapped wetlands intersect it. This is a correct answer, not an error. The golden fixture test must not fail on empty results.

10. **Do not re-add FEMA NFHL.** It is already in the catalog from Phase 2.

## Build order

**Step 1 — Source discovery (do this before writing any YAML)**

Fetch the service root for each new source. Record its spatial reference and confirm the layer structure. Use this exact pattern:

```
GET https://{service_base_url}?f=json
```

Look for `"spatialReference": { "wkid": ... }` in the response. Check that the layer you intend to query exists.

Sources to verify:
```
WA DNR:     https://gis.dnr.wa.gov/site3/rest/services/Public_Boundaries/WADNR_PUBLIC_Cadastre_OpenData/MapServer?f=json
WA Ecology: https://fortress.wa.gov/ecy/gispublic/rest/services/Wetlands/WADOE_ECY_Wetlands/MapServer?f=json
WA Ecology: https://fortress.wa.gov/ecy/gispublic/rest/services/WR/WADOE_ECY_WaterRights/MapServer?f=json
WA DOT:     https://data.wsdot.wa.gov/arcgis/rest/services/Shared/CountyBoundaries/MapServer?f=json
WA DFW:     https://fortress.wa.gov/dfw/public/publicwdfw/rest/services/PHS/WDFW_PHS/MapServer?f=json
USGS:       https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer?f=json
BLM:        https://gis.blm.gov/arcgis/rest/services/lands_and_realty/BLM_Natl_SMA_Surface_Management_Agency/MapServer?f=json
USFS:       https://apps.fs.usda.gov/arcgis/rest/services/EDW/EDW_ForestSystemBoundaries_01/MapServer?f=json
```

Record what you find. If a URL returns 404 or non-JSON, try variations (MapServer vs FeatureServer, different path) for up to 5 minutes. If still unresolvable, mark it `needs_verification` and move on.

**Step 2 — Write `catalog/seeds/wa_state.yaml`**

Use verified endpoints and spatial references from Step 1. Match the schema of existing seeds in `catalog/seeds/skagit.yaml`.

**Step 3 — Write `catalog/seeds/federal_gis.yaml`**

Same pattern.

**Step 4 — Update seed script and reseed**

Add the two new files to `catalog/seeds/seed.py`. Reseed:

```bash
python catalog/seeds/seed.py --env local
sqlite3 catalog/local.db "SELECT id, name FROM sources WHERE active=1 ORDER BY id;"
```

Confirm all new sources appear.

**Step 5 — arcgis_adapter: add ImageServer support**

In `workers/arcgis-adapter/src/index.ts`, add the `server_type` field to `ArcGISRequest` and the ImageServer `/identify` path. This is a backward-compatible addition — existing behavior unchanged. See the brief for the full spec.

After the change, run:
```bash
cd workers/arcgis-adapter && npm run typecheck
```

**Step 6 — Update planner**

In `agent/planner.py`, extend the domains list and add state/federal routing guidance. See the brief for the exact text additions. Do not change anything else in planner.py.

**Step 7 — Write `catalog/tools/verify_sources.py`**

This is a maintenance script that pings every active source and reports reachability, spatial reference, and layer count. Run it after writing:

```bash
python catalog/tools/verify_sources.py
```

Expected: a table showing each source, whether it's reachable, and its spatial reference. Any source marked `needs_verification` in the YAML should show as unreachable — confirming the flag is correct.

**Step 8 — Golden fixture and test**

Write `agent/tests/fixtures/p48165_wetlands_expected.json` exactly as specified in the brief.

Add the wetlands live test to `agent/tests/test_golden.py` behind `RUN_LIVE_GOLDEN=1`.

## After each step

```bash
python -m pytest agent/tests/ -v
```

All 17 existing tests must pass. Phase 3 adds 0 new unit tests (only the live golden fixture test).

## When a service is unreachable

1. Set `status: "needs_verification"` in the YAML entry
2. Leave `layer_id: 0` and add a `note:` explaining what you tried
3. Continue to the next source
4. After all sources are processed, add a section to `README.md`:

```markdown
## Sources Pending Verification

The following sources are in the catalog but could not be verified 
during Phase 3 implementation. They will return structured errors 
gracefully until confirmed and updated.

| Source ID | Issue | Last checked |
|-----------|-------|--------------|
| ...       | ...   | ...          |
```

## Definition of done

- [ ] `python -m pytest agent/tests/ -v` — 17 passed, 2 skipped (no regressions)
- [ ] `python catalog/seeds/seed.py --env local` completes without error
- [ ] `sqlite3 catalog/local.db "SELECT count(*) FROM sources WHERE active=1;"` returns 12+
- [ ] `python catalog/tools/verify_sources.py` runs and outputs a status table
- [ ] At least 6 new sources are reachable per the verification table
- [ ] `npm run typecheck` passes in `workers/arcgis-adapter/`
- [ ] `POST /ask "Are there wetlands on P48165?"` runs without error
- [ ] `POST /ask "Is P48165 near federal land?"` includes a BLM or USFS step in evidence
- [ ] `README.md` has a `## Sources Pending Verification` section (even if empty)
- [ ] No new Worker directories were created
- [ ] No new Python adapter files were created
- [ ] `RUN_LIVE_GOLDEN=1 python -m pytest agent/tests/test_golden.py -v` passes for wetlands fixture
