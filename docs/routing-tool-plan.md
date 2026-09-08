# OpenSkagit Field Routing Tool

## Product goal

Provide a staff-only route workspace for 2,000–3,000 GIS parcel records. A plan
is imported once, clustered into routes of approximately 50–75 stops, reviewed
and edited, and optimized when the crew is ready. The tool produces stop order
and map geometry; it does not need turn-by-turn directions.

## Operating model

1. Import and validate the original CSV/XLSX without losing source columns.
2. Create geographic clusters only. Save the plan immediately.
3. Review route cards and the map. Move, add, remove, lock, or split stops.
4. Optimize one route or all unlocked routes on demand.
5. Save each optimization as a new plan revision and export the final order.

## Build sequence

- [ ] **1. Stable routing foundation** — use the existing Django app, PostGIS
  database, Railway web service, private Valhalla service, Leaflet, and CARTO
  basemap. Replace full matrices with Valhalla `optimized_route` per route.
- [ ] **2. Map presentation** — display a working street/aerial basemap,
  colored route polylines, numbered stops, route visibility, and selected-route
  highlighting.
- [ ] **3. Saved workspace** — list recent imports and plans, reopen a plan by
  ID, show clustered/optimized status, timestamps, and algorithm version.
- [ ] **4. Route-level controls** — add optimize-this-route, optimize-all,
  reset order, reverse order, lock/unlock, and per-route export controls.
- [ ] **5. Editing** — support moving stops between routes, adding/removing
  stops from the imported set, route splitting/merging, and an edit history.
- [ ] **6. Walking mode** — use pedestrian costing and add street-name and
  side-of-street sequencing heuristics, with a visible low-confidence warning.
- [ ] **7. Operational safeguards** — validate coordinate coverage, show
  unreachable stops, prevent accidental overwrite, add plan revision labels,
  and test with the supplied 310-row export and larger synthetic files.

## Acceptance checkpoints

- A 291-stop import can be clustered without calling Valhalla.
- A saved plan can be reopened days later with identical assignments.
- Optimizing a 60-stop route does not request a 3,600-cell matrix.
- A route line and a usable basemap appear for every route with valid points.
- Moving a stop marks the affected routes as needing optimization.
- A failed routing-server request gives a useful message and preserves the
  clustered plan.

## Current implementation note

The prototype has the import and persistence foundation. The next code pass
should complete items 1–3 before expanding the editing UI. Existing unrelated
worktree changes must remain outside routing commits.
