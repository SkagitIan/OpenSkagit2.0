# OpenSkagit MCP Release Checklist

Created: 2026-08-01  
Status: active; no production release authorized by this checklist alone

Every checked item requires linked evidence. A code change, green unit test, or
successful deployment is not by itself evidence that a phase exit gate passed.

## Phase 0 - scope and authority

- [x] Canonical repository, endpoint, store, branch, and revision recorded.
- [x] Exact 31-tool runtime baseline frozen.
- [x] Exact 14-tool target expansion recorded.
- [x] Registry, handlers, MCP publication, commands, tests, and manifests inventoried.
- [x] Public catalog, OAuth metadata, and fail-closed unauthenticated behavior probed.
- [x] Railway services, environment count, replicas, health configuration, domains, and volumes inventoried.
- [x] Aggregate source freshness and adoption recorded without payloads/secrets.
- [x] Deployment manifest authority decided.
- [x] Consumer and retirement-candidate matrix recorded.
- [x] Risk and decision logs created.
- [x] Product, platform, source-data, security/privacy, and operations owner assigned: Ian.
- [x] Compatibility/deprecation policy and 90-day minimum overlap approved by Ian.
- [x] Phase 0 exit gate accepted by Ian on 2026-08-01.

## Phase 1 - local-first release safety

- [ ] Separate local development PostGIS documented and reproducible.
- [ ] Disposable CI PostGIS created; production DB cannot be selected accidentally.
- [ ] Local ASGI application exercises MCP, Django, OAuth discovery, and lifespan.
- [ ] Dedicated local OAuth/storage/notification settings proven safe.
- [ ] Dependency lock and intentional update workflow checked in.
- [ ] CI runs checks, unit/integration/contract/protocol tests, scans, and production-equivalent build.
- [ ] Migrations and one-time work separated from normal web startup.
- [ ] Liveness and readiness implemented and tested independently.
- [ ] On-demand Railway release-candidate environment isolated from production identity data and credentials.
- [ ] Candidate health check rejects an intentionally failing release.
- [ ] Candidate rollback restores the previous version without data/credential loss.
- [ ] Operator commands work from a clean supported session.
- [ ] Phase 1 evidence and owner approval recorded.

## Phases 2-3 - contract and source truth

- [ ] Tool registry includes versions, stability, ownership, sensitivity, limits, deadlines, pagination, cache, and limitations.
- [ ] Source registry includes authority, coverage, attribution/license, refresh, stale threshold, schema fingerprint, fallback, and sensitivity.
- [ ] Durable sanitized source status records attempts, successes, effective/verified dates, quality, and failures.
- [ ] Error taxonomy and protocol/result placement policy approved.
- [ ] Generated catalogs and snapshots exactly match `tools/list` and handlers.
- [ ] CI fails on all catalog/source drift classes.
- [ ] `effective_at`, `verified_at`, and `served_at` are distinct.
- [ ] Every stable tool returns truthful provenance, coverage, freshness, warning, and error state.
- [ ] GIS, zoning, budget, Land Ledger, tax, and live-source verification schedules run and alert named owners.
- [ ] Assessor warning and PostGIS invariant thresholds are approved and passing.

## Phases 4-5 - hardening and verification

- [ ] Per-tool argument, row, geometry, byte, concurrency, rate, and deadline limits enforced.
- [ ] Upstream timeouts, retries, quotas, caching/circuit behavior, and cancellation proven.
- [ ] `gis_query_layer` public safety approved or tool versioned/privatized with migration plan.
- [ ] OAuth PKCE, redirects, expiry, rotation/replay, revocation, scope, host/origin, and redaction tests pass.
- [ ] Encryption key rotation strategy approved and exercised.
- [ ] Adopted SLO passes representative topology load test.
- [ ] All 31 tools have authenticated Streamable HTTP golden/failure/limit/freshness tests.
- [ ] Sanitized parser fixtures and disposable PostGIS query-plan tests pass.
- [ ] `check_unified_mcp_catalog` meets its environment/auth/timeout/JSON specification.
- [ ] Low-privilege production canary runs without payload/argument telemetry.

## Phases 6-8 - catalog expansion, operations, onboarding

- [ ] Each of 14 additions passes product, methodology, privacy, source, performance, and operations review.
- [ ] Generated registry/handlers/docs/snapshot/`tools/list` show exact 45-tool parity.
- [ ] Dashboards, alerts, retention, cleanup, cost/capacity reporting, and named response ownership work.
- [ ] Database/object-storage backups and isolated restore meet approved RPO/RTO.
- [ ] Incident and credential-rotation exercises pass.
- [ ] `/mcp/` provides accessible Add to ChatGPT and Add to Claude instruction/link behavior based on current official contracts.
- [ ] Access request flow, no-secret tests, browser/accessibility tests, and privacy-safe onboarding analytics pass.
- [ ] Approved reference clients complete real sessions or external account/admin blockers are recorded truthfully.

## Phases 9-10 - beta, cutover, and retirement

- [ ] Real approved workflows meet SLO and usability expectations.
- [ ] Every legacy contract maps to a tested replacement or approved discontinuation.
- [ ] Railway/OAuth/Cloudflare/owner evidence identifies consumers.
- [ ] Authenticated Cloudflare versions/routes/traffic/crons/D1/R2/bindings/secret-name inventory exported.
- [ ] Unique D1/R2/legacy state backed up and verified.
- [ ] Known consumers migrated and canonical calls observed.
- [ ] Trustworthy zero-legacy-traffic observation window completed.
- [ ] Each retirement target has replacement, parity, consumer, traffic, data, backup, route, credential, rollback, and approver evidence.
- [ ] Shutdown occurs in dependency order with smoke/canary after each step.
- [ ] Component-only credentials revoked last; shared credentials rotated safely.
- [ ] Rollback windows expire before source/storage deletion.
- [ ] Final catalog, inventory, register, backups, runbooks, and acceptance record reconciled.
- [ ] Product, data/methodology, security/privacy, and operations final acceptance signed.

## Automatic stops

Stop before any action involving an unknown target, production identity-data copy,
breaking stable contract without migration, new public scope/mutation, sensitive
graph/owner exposure, material unapproved cost, production credential rotation,
volume/bucket/database deletion, route/domain removal, or retirement without the
complete evidence packet and owner approval.
