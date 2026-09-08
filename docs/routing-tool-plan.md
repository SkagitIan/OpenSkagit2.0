# OpenSkagit Field Routing Tool

## Product goal

Provide a staff-only route workspace for 2,000–3,000 GIS parcel records. A plan
is imported once, clustered into routes of approximately 50–75 stops, reviewed
and edited, and optimized when the crew is ready. The tool produces stop order
and map geometry; it does not need turn-by-turn directions.

## Operating model

1. Import and validate the original CSV/XLSX without losing source columns.
2. Create geographic clusters only. Save the plan immediately.
3. Review route cards and the map. Move, add, remove, or split stops.
4. Optimize one route or all routes on demand, using each route's selected mode.
5. Save each optimization as a new plan revision and export the final order.

## Build sequence

- [x] **1. Stable routing foundation** — use the existing Django app, PostGIS
  database, Railway web service, private Valhalla service, Leaflet, and CARTO
  basemap. Replace full matrices with Valhalla `optimized_route` per route.
- [x] **2. Map presentation** — display a working street/aerial basemap,
  colored route polylines, numbered stops, route visibility, and selected-route
  highlighting.
- [x] **3. Saved workspace** — list recent imports and plans, reopen a plan by
  ID, show clustered/optimized status, timestamps, and algorithm version.
- [x] **4. Route-level controls** — add optimize-this-route, optimize-all,
  reset order, reverse order, per-route mode, and per-route export controls.
- [ ] **5. Editing** — moving stops between routes and adding/removing stops are
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

Creating clusters immediately saves a named `RoutingPlan` with route and stop
records. Later optimization and field edits update that same plan and append a
`RoutingPlanRevision` snapshot, so the plan can be reopened without repeating
the import or clustering step. Existing unrelated worktree changes must remain
outside routing commits.
