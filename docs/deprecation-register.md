# OpenSkagit Deprecation Register

Status: active; safe migrations underway, destructive retirement awaiting traffic/data gates
Date: 2026-07-16

`DELETE` means remove deployment and source after every gate passes. It does not authorize immediate deletion before verification.

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| `KEEP` | Canonical component. |
| `MERGE` | Move unique behavior/data to canonical owner. |
| `BRIDGE` | Temporary compatibility layer; no new domain behavior. |
| `FREEZE` | Security and bug fixes only. |
| `ARCHIVE` | Read-only reference/rollback; not deployed. |
| `DELETE` | Remove after gates and owner approval. |
| `VERIFY` | Deployment, traffic, data, or consumers remain unknown. |

## Decisions

| Component | Decision | Replacement/owner | Evidence required before removal |
| --- | --- | --- | --- |
| `OpenSkagit-railway` | `KEEP` | Canonical platform | N/A |
| `openskagit_tools` unified MCP | `KEEP` | Canonical tool façade in Django ASGI | Publish at `/mcp/api/`, monitor usage, then retire compatibility MCPs |
| Railway PostgreSQL/PostGIS | `KEEP` | Canonical store | N/A |
| `assessor_sync` | `KEEP` | Same | Freshness and failure alerts |
| `assessor_mcp.services` | `KEEP` | Shared live parcel service | Contract and parser fixture coverage |
| Separate `assessor-mcp` process | `BRIDGE` -> `DELETE` | Unified MCP | All clients moved; compatibility window passed |
| `gis_mcp.services` | `KEEP` | Shared GIS service | Source verification and cache policy |
| Separate `gis-mcp` process | `BRIDGE` -> `DELETE` | Unified MCP | All clients moved; compatibility window passed |
| `zoning_mcp.services`/corpus | `KEEP` | Shared zoning service | Coverage and citation tests |
| Separate `zoning-mcp` process | `BRIDGE` -> `DELETE` | Unified MCP | All clients moved; compatibility window passed |
| `mcp_django.py` | `KEEP`, local only | Admin tooling | Prove no public/production exposure |
| `opportunity` | `KEEP` | Same | Maintain feature boundary |
| `ask_agent` remote MCP bridge | `MERGE` (context cut over) | Direct services + external MCP client | Migrate remaining property/GIS tools; behavioral tests |
| `OpenSkagit/worker` | `BRIDGE` -> `DELETE` | Railway context/GIS + unified MCP | Census/soils moved; migrate remaining consumers, cut routes, prove zero traffic |
| `workers/arcgis-adapter` | `FREEZE` -> `DELETE` unless edge value proven | GIS/source client | Consumers, caching, CORS, rate-limit, egress evidence |
| `workers/web-adapter` | `VERIFY` | Source client or thin proxy | Identify sources requiring Cloudflare egress |
| `workers/notify-adapter` | `KEEP` provisionally | Notification boundary | Confirm usage; add auth, retries, ownership |
| `skagit-pipeline` | `FREEZE` -> `DELETE` | PostGIS, assessor sync, unified tools | Parity, unique-field decision, cutover, backup, 30 zero-traffic days |
| `cloudflared` | `VERIFY` -> `DELETE` | None | Confirm deployment; preserve unique data; remove routes |
| Older `OpenSkagit/agent` | `MERGE` -> `ARCHIVE` -> `DELETE` | `ask_agent` + source registry | Migrate verifier/catalog; decide case-file retention |
| `OpenSkagit/catalog` and `registry` | `MERGE` -> delete duplicates | One Railway source registry | Source-ID mapping and tests |
| `OpenSkagit/frontend` | `VERIFY` -> `DELETE` | Railway UI | Confirm no deployed Pages site/users; preserve needed assets |
| Top-level `Factory/mcp` | `ARCHIVE` -> `DELETE` | `assessor_mcp.services` | Schema/parser parity; fixtures retained; no consumers |

## Data And Infrastructure

| Asset | Decision | Conditions |
| --- | --- | --- |
| D1 `skagit-parcels` | `FREEZE` -> `DELETE` | Export, unique fields resolved, 30 zero-traffic days, approval |
| R2 `raw-parcels` | `VERIFY` | Inventory objects, retention purpose, and consumers |
| Duplicate `skagit-parcels` configs | `DELETE` | Determine deployed state; remove routes/cron safely |
| Multiple GIS/source catalogs | `MERGE` | One schema and ID map; generated runtime records verified |
| Legacy debug HTML/JSON/HAR | `VERIFY` -> delete or sanitized fixture | Confirm no private/session data; retain minimum fixtures |
| Old Worker secrets/tokens | delete/rotate | Shutdown complete; replacement credentials verified |

## Per-Component Checklist

- [ ] Confirm deployed/not-deployed state.
- [ ] Identify callers, routes, domains, crons, queues, stores, buckets, and secrets.
- [ ] Record replacement or intentional discontinuation.
- [ ] Pass contract/parity tests.
- [ ] Migrate, back up, or approve deletion of unique data.
- [ ] Cut over consumers and observe production.
- [ ] Confirm zero traffic for required window.
- [ ] Remove routes, schedules, bindings, and environment references.
- [ ] Revoke or rotate component-only credentials.
- [ ] Pass smoke tests after shutdown.
- [ ] Expire rollback window.
- [ ] Obtain owner approval for source/local-directory deletion.
- [ ] Update catalog and register.

## Proposed Cleanup Order

1. Verify and delete `cloudflared` if not deployed or unique.
2. Retire top-level `mcp` after assessor parser parity.
3. Consolidate source catalogs and retire duplicates.
4. Migrate Census/soils and cut over `skagit-agent-worker`.
5. Move D1 consumers to PostGIS, freeze, observe, back up, and delete pipeline infrastructure.
6. Remove separate MCP process entries after unified façade adoption.
7. Review web/notification Workers based on measured value.

## 2026-07-16 Gate Evidence

- Replacement: canonical `context_get_census` and `context_get_soils` are implemented and covered by the unified registry tests.
- Consumer cutover: Ask Agent now calls the Railway services in-process for Census and soils.
- Parity/correction: P96023 returned ACS 2024 five-year results at four geography levels and one NRCS map unit. The replacement fixes the legacy Worker's missing Census key and invalid `muaggatt.farmlndcl` query.
- Usage evidence: new canonical calls are recorded in `McpToolCall`; OAuth clients/grants already record last use.
- Still open: authenticated Cloudflare traffic, route, secret-name, D1, R2, and cron export; remaining consumers; observation window; backups; route/binding removal; credential revocation.
- Deletion decision: **not yet safe**. Public reachability is not proof of use or non-use.

## Approval Record

| Component | Final decision | Approved by | Date | Backup/rollback reference |
| --- | --- | --- | --- | --- |
| _pending_ |  |  |  |  |
