# OpenSkagit Deployment Evidence — 2026-07-16

This file separates observed production behavior from source configuration and unknown account state. It is evidence for consolidation, not authorization to bypass retirement gates.

## Canonical Railway surface

- Public catalog: `https://openskagit.com/mcp/`
- Authenticated MCP: `https://openskagit.com/mcp/api/`
- Deployment owner: `OpenSkagit-railway` Django ASGI service
- Authentication: OAuth authorization code with PKCE, approved clients, `openskagit.read`, revocable grants
- Tool registry after this migration: 25 read-only tools

The current recovery deployment `021b10ec-f20d-489b-9fc9-b663649e075d` completed successfully on the proven Nixpacks configuration. Read-only checks returned HTTP 200 for `/` and `/mcp/`, and the expected HTTP 401 for unauthenticated `/mcp/api/`. An authenticated short-lived OAuth client discovered all 25 tools, including `parcel_search`, and called the canonical parcel search without an MCP error. The client and grant were deleted immediately; secret-free telemetry retained the test calls.

## Cloudflare public probes

| Worker hostname | Root probe | Source-configured role | Disposition |
| --- | --- | --- | --- |
| `skagit-agent-worker.ian-larsen-1976.workers.dev` | HTTP 200 | Legacy HTTP MCP/property/GIS/context | Bridge, then delete |
| `skagit-parcels.ian-larsen-1976.workers.dev` | HTTP 200 | D1/R2 parcel pipeline | Freeze; parity/export/observe/delete |
| `arcgis-adapter.ian-larsen-1976.workers.dev` | HTTP 200 | ArcGIS proxy | Delete unless measured edge value exists |
| `web-adapter.ian-larsen-1976.workers.dev` | HTTP 200 | Web proxy | Verify consumers and egress need |
| `notify-adapter.ian-larsen-1976.workers.dev` | HTTP 404 at root | POST notification boundary | Verify actual route/auth/retries/traffic |

The legacy Census endpoint matched the parcel to geographies but ACS requests failed because no Census API key was supplied. The legacy soils query failed because farmland classification was read from the wrong NRCS table. Both behaviors now have tested Railway replacements.

Safe method probes and source inspection found that `arcgis-adapter`, `web-adapter`, and `notify-adapter` accept public unauthenticated requests. The ArcGIS and web adapters accept caller-selected upstream targets, and the notification adapter accepts caller-selected delivery targets. Current Railway services have no variables pointing to these adapters, and the old FastAPI agent that references them is not present in the deployed Railway service list. Treat all three as frozen urgent retirement candidates, but do not disable them until Cloudflare traffic/routes and external consumers are verified.

## Source-configured Cloudflare assets

- Workers: `skagit-agent-worker`, `skagit-parcels`, `arcgis-adapter`, `web-adapter`, `notify-adapter`
- Duplicate `skagit-parcels` Wrangler configurations: `OpenSkagit/skagit-pipeline` and `OpenSkagit/cloudflared`
- D1 binding: `skagit-parcels`, database id `bd1fd2cb-9d82-4068-a79a-de55c83cc981`
- R2 binding: `raw-parcels`
- Pipeline cron: `30 11 * * *`

These facts come from source configuration and do not prove which account resources or bindings remain active.

None of the checked-in Wrangler files declares an `openskagit.com` custom route. The public site is separately proxied by Cloudflare to the Railway origin, as shown by Cloudflare response headers together with `X-Railway-Request-Id`. Retiring a standalone `*.workers.dev` Worker must never remove or change the `openskagit.com` DNS/proxy configuration.

`OpenSkagit/skagit-pipeline` is a separate Git repository (`SkagitIan/skagit-pipeline`). Its `Weekly Parcel Ingest` GitHub Actions workflow is currently `disabled_inactivity`. The last scheduled run on 2026-07-12 generated the import successfully but failed in the remote D1 import step with `D1_RESET_DO`; Wrangler stated the failed transaction would return the database to its original state. The preceding scheduled runs also failed. This is evidence that the GitHub writer is effectively frozen, not evidence that the Worker cron or every other writer is inactive. The sibling `OpenSkagit/cloudflared` directory is untracked and is not a nested Git repository, so its local workflow file is not active from the parent repository.

## D1/PostGIS baseline

- Public D1 `/health`: 83,509 `parcel_cards` rows.
- Canonical PostGIS: 83,391 active parcels and 83,638 total parcels.
- D1 is therefore 118 rows above the active PostGIS population and 129 rows below the all-status PostGIS population. The difference must be classified before export/deletion; it is not evidence of simple parity.
- Golden parcel P96023 exists in both stores. Its D1 normalized columns are largely null while current assessor values are embedded in a JSON field under an unrelated column, whereas PostGIS exposes the current assessed/market/land values as typed columns. This confirms that the deployed D1 shape is not an equivalent analytical source.
- Public `/parcels`, `/health`, and `/parcel/P96023` routes respond, but the parcel payload does not match either checked-in `skagit-parcels` Worker implementation exactly. Authenticated deployed-version inventory is required to identify the actual production source revision.
- A deterministic 25-parcel audit received all 25 D1 records without request failures. None had complete normalized core fields; every record embedded assessor JSON under `days_since_last_sale`. Recovered assessed, total-market, and building values matched PostGIS, while acreage mismatched for 10 records and sale price mismatched for one. Re-run with `python manage.py audit_legacy_d1 --sample-size 25`.

## Account-level blocker

Wrangler authentication is expired (`whoami` returns HTTP 400 / not logged in). Therefore traffic analytics, deployed versions, routes, secret names, D1 counts, R2 inventory, and cron execution history remain unverified. Restore Wrangler login or provide a read-only Cloudflare token before deleting any Worker or storage asset.

Railway consumer inspection is complete for the currently deployed project: the active web and job services have no legacy Worker/adapter URL variables, and no separate legacy FastAPI agent or standalone assessor/GIS/zoning MCP service appears in the service list. In canonical source, the only remaining `skagit-parcels` URL is the intentional read-only `audit_legacy_d1` default. External consumers outside Railway remain unknown until Cloudflare traffic can be exported.

The production 30-day MCP usage report currently contains three successful controlled OAuth smoke calls and no failures: `context_get_census` (755 ms), `context_get_soils` (468 ms), and `parcel_search` (14 ms). No other canonical calls have been recorded yet. This proves telemetry and replacement execution, but it does not yet prove external adoption or satisfy a 30-day observation window.

## Railway hardening finding

The Railway/Nixpacks build emitted Docker warnings that multiple runtime secrets were promoted into generated image-build `ARG`/`ENV` instructions, including application, R2, notification, and API credentials. No secret values were printed in the observed logs. A repository-owned Dockerfile removed those warnings but was reverted after its command/static-file boundary caused a production 502. Railway is back on the proven Nixpacks configuration. Resolve build-variable isolation as a separate staged change with a non-production verification environment, then rotate affected credentials.

## Next retirement evidence

1. Export Cloudflare account inventory and 30-day traffic per route/Worker without modifying the `openskagit.com` zone/proxy.
2. Run `python manage.py report_mcp_usage --days 30` for the canonical endpoint.
3. Identify and migrate every remaining caller of the Worker/property pipeline.
4. Compare D1/PostGIS schema, counts, and a golden parcel sample; export D1/R2.
5. Freeze legacy writes and observe zero reads/writes for 30 days.
6. Remove routes, cron, bindings, and component-only secrets; smoke test; expire rollback window; delete source.
