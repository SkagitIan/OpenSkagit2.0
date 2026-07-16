# OpenSkagit Deployment Evidence — 2026-07-16

This file separates observed production behavior from source configuration and unknown account state. It is evidence for consolidation, not authorization to bypass retirement gates.

## Canonical Railway surface

- Public catalog: `https://openskagit.com/mcp/`
- Authenticated MCP: `https://openskagit.com/mcp/api/`
- Deployment owner: `OpenSkagit-railway` Django ASGI service
- Authentication: OAuth authorization code with PKCE, approved clients, `openskagit.read`, revocable grants
- Tool registry after this migration: 24 read-only tools

Deployment `8289dc44-519e-4410-821a-05e6264ee7a0` completed successfully. A short-lived OAuth client discovered all 24 tools and called both new context tools for P96023 without MCP errors. The client and grant were deleted immediately; secret-free telemetry retained one successful call for each tool (755 ms Census, 468 ms soils).

## Cloudflare public probes

| Worker hostname | Root probe | Source-configured role | Disposition |
| --- | --- | --- | --- |
| `skagit-agent-worker.ian-larsen-1976.workers.dev` | HTTP 200 | Legacy HTTP MCP/property/GIS/context | Bridge, then delete |
| `skagit-parcels.ian-larsen-1976.workers.dev` | HTTP 200 | D1/R2 parcel pipeline | Freeze; parity/export/observe/delete |
| `arcgis-adapter.ian-larsen-1976.workers.dev` | HTTP 200 | ArcGIS proxy | Delete unless measured edge value exists |
| `web-adapter.ian-larsen-1976.workers.dev` | HTTP 200 | Web proxy | Verify consumers and egress need |
| `notify-adapter.ian-larsen-1976.workers.dev` | HTTP 404 at root | POST notification boundary | Verify actual route/auth/retries/traffic |

The legacy Census endpoint matched the parcel to geographies but ACS requests failed because no Census API key was supplied. The legacy soils query failed because farmland classification was read from the wrong NRCS table. Both behaviors now have tested Railway replacements.

## Source-configured Cloudflare assets

- Workers: `skagit-agent-worker`, `skagit-parcels`, `arcgis-adapter`, `web-adapter`, `notify-adapter`
- Duplicate `skagit-parcels` Wrangler configurations: `OpenSkagit/skagit-pipeline` and `OpenSkagit/cloudflared`
- D1 binding: `skagit-parcels`, database id `bd1fd2cb-9d82-4068-a79a-de55c83cc981`
- R2 binding: `raw-parcels`
- Pipeline cron: `30 11 * * *`

These facts come from source configuration and do not prove which account resources or bindings remain active.

## D1/PostGIS baseline

- Public D1 `/health`: 83,509 `parcel_cards` rows.
- Canonical PostGIS: 83,391 active parcels and 83,638 total parcels.
- D1 is therefore 118 rows above the active PostGIS population and 129 rows below the all-status PostGIS population. The difference must be classified before export/deletion; it is not evidence of simple parity.
- Golden parcel P96023 exists in both stores. Its D1 normalized columns are largely null while current assessor values are embedded in a JSON field under an unrelated column, whereas PostGIS exposes the current assessed/market/land values as typed columns. This confirms that the deployed D1 shape is not an equivalent analytical source.
- Public `/parcels`, `/health`, and `/parcel/P96023` routes respond, but the parcel payload does not match either checked-in `skagit-parcels` Worker implementation exactly. Authenticated deployed-version inventory is required to identify the actual production source revision.
- A deterministic 25-parcel audit received all 25 D1 records without request failures. None had complete normalized core fields; every record embedded assessor JSON under `days_since_last_sale`. Recovered assessed, total-market, and building values matched PostGIS, while acreage mismatched for 10 records and sale price mismatched for one. Re-run with `python manage.py audit_legacy_d1 --sample-size 25`.

## Account-level blocker

Wrangler authentication is expired (`whoami` returns HTTP 400 / not logged in). Therefore traffic analytics, deployed versions, routes, secret names, D1 counts, R2 inventory, and cron execution history remain unverified. Restore Wrangler login or provide a read-only Cloudflare token before deleting any Worker or storage asset.

## Railway hardening finding

The Railway/Nixpacks build emitted Docker warnings that multiple runtime secrets were promoted into generated image-build `ARG`/`ENV` instructions, including application, R2, notification, and API credentials. No secret values were printed in the observed logs. A repository-owned Dockerfile removed those warnings but was reverted after its command/static-file boundary caused a production 502. Railway is back on the proven Nixpacks configuration. Resolve build-variable isolation as a separate staged change with a non-production verification environment, then rotate affected credentials.

## Next retirement evidence

1. Export Cloudflare account inventory and 30-day traffic per route/Worker.
2. Run `python manage.py report_mcp_usage --days 30` for the canonical endpoint.
3. Identify and migrate every remaining caller of the Worker/property pipeline.
4. Compare D1/PostGIS schema, counts, and a golden parcel sample; export D1/R2.
5. Freeze legacy writes and observe zero reads/writes for 30 days.
6. Remove routes, cron, bindings, and component-only secrets; smoke test; expire rollback window; delete source.
