# OpenSkagit Production MCP Plan

Status: active execution plan  
Plan date: 2026-08-01  
Canonical repository: `OpenSkagit-railway`  
Canonical endpoint: `https://openskagit.com/mcp/api/`  
Canonical analytical store: Railway PostgreSQL/PostGIS  
Initial GA catalog: 31 existing read-only tools  
Target catalog: 45 public read-only tools

## Purpose

This document is the authoritative execution plan for taking the existing OpenSkagit MCP implementation from a working authenticated production endpoint to a singular, production-quality service with complete contracts, source provenance, operational controls, test evidence, client adoption, and safe retirement of legacy infrastructure.

The target is one supported MCP product, not one large implementation module. Domain behavior remains in the Django app that owns it. `openskagit_tools` owns the public contract, transport, authentication, common envelope, source catalog, error mapping, and cross-domain operating policy.

This plan is written so a Codex implementation session can execute one phase at a time. Each phase includes explicit Codex goals, required evidence, an exit gate, and stop conditions. Codex must not mark a phase complete merely because code was written; the phase is complete only when its exit evidence exists and has been verified.

## Production Outcome

The completed platform will have:

- One canonical HTTPS Streamable HTTP MCP endpoint.
- OAuth authorization-code authentication with PKCE, refresh rotation, revocation, and a stable public read scope.
- One generated, versioned tool catalog shared by MCP discovery, documentation, tests, and operations.
- PostGIS as the canonical store for imported and analytical parcel data.
- Modular parcel, GIS, context, zoning, budget, Opportunity, tax, Land Ledger, and source-health services.
- Truthful source provenance, coverage, and freshness on every response.
- Enforced request, query, geometry, concurrency, rate, response-size, and deadline limits.
- Automated contract, parser, PostGIS, authenticated protocol, load, and production canary tests.
- Dashboards, alerts, recovery procedures, and named operational ownership.
- An authoritative public **/mcp/** onboarding page with accessible **Add to ChatGPT** and **Add to Claude** actions, verified client-specific instructions, and a safe manual fallback whenever a vendor does not publish a supported install link.
- Measured client adoption followed by safe retirement of redundant MCP processes, Workers, D1/R2 assets, schedules, bindings, and component-only credentials.

## Current Verified Baseline

This is a dated snapshot, not a substitute for Phase 0 verification.

| Area | Verified state on 2026-08-01 |
| --- | --- |
| Public catalog | `https://openskagit.com/mcp/` returns 200 and advertises 31 tools. |
| OAuth discovery | Authorization-server and protected-resource metadata return 200. |
| Authentication boundary | An unauthenticated MCP `initialize` request returns 401. |
| Railway deployment | The July 31 web and PostGIS deployments report success. |
| Web topology | One web replica; no Railway health-check path is configured. |
| Local unified tests | 24 `openskagit_tools` tests pass. |
| Contract documentation | Runtime registry has 31 tools; `platform-catalog.md` still reports 25. |
| Unified smoke command | `check_unified_mcp_catalog` exists as an alias to a seven-case in-process checker, but lacks the authenticated protocol and environment coverage required by Phase 5. |
| MCP adoption | The 30-day production report contains only three controlled calls from 2026-07-16. |
| Assessor sync | Run 46 succeeded on 2026-08-01; the land step reported 3,895 warnings. |
| Downloadable GIS sources | Enabled sources were last downloaded/checked on 2026-07-13. |
| Land Ledger | One city, Sedro-Woolley, rebuilt on 2026-06-18. |
| Tax delinquency | Latest backfill completed 2026-06-26 with 106,223 saves and 757 per-item errors. |
| Scheduled data work | No active Railway tax slow-check or Land Ledger rebuild service was found. |
| Environments and CI | Railway exposes production only; no checked-in GitHub CI workflow or dependency lock is present. |
| Cloudflare retirement evidence | Wrangler authentication remains unavailable, blocking traffic, route, cron, D1, R2, binding, and secret-name verification. |

## Architecture Boundaries

### Canonical ownership

| Capability | Owning app/module | MCP rule |
| --- | --- | --- |
| Unified contracts, transport, OAuth, envelopes, telemetry | `openskagit_tools` | May coordinate and delegate; must not absorb domain implementations. |
| Bulk assessor sync and audit | `assessor_sync` | Expose status/freshness only; never expose sync/import controls publicly. |
| Live county parcel facts | `assessor_mcp.services` | Reuse one parser/service implementation. |
| GIS layers and overlays | `gis_mcp.services` | Registered and bounded sources only. |
| Census and soils | `context_mcp.services` | Preserve area-level and screening caveats. |
| Zoning profiles and cited screening | `zoning_mcp.services` | Never describe screening output as a legal or entitlement determination. |
| Reviewed public budgets | `budgets.services` | Preserve fiscal year, document status, and page evidence. |
| Opportunity screens | `opportunity` | Deterministic, bounded, explainable signals only. |
| Parcel tax analysis | `taxtool` | Make tax year and methodology explicit. |
| Delinquency checks | `tax_delinquency` | Include the statement verification date and stale-state warning. |
| Land Ledger | `land_ledger` | Expose generated results, assumption version, coverage, and rebuild time. |
| Graph/entity resolution | `graph` | Keep identity linkage internal; only separately reviewed anonymous aggregates may cross the public boundary. |
| Generic analyst SQL | `ask_agent` or approved internal tooling | No arbitrary SQL in `openskagit.read`. |

### PostGIS rules

- Treat parcel identifiers as text.
- Use `skagit_parcels.parcel_number` as the canonical parcel identity.
- Join GIS parcels with `gis_skagit_parcels.parcel_id = skagit_parcels.parcel_number`.
- Join primary zoning with `parcel_primary_zoning.parcel_id = skagit_parcels.parcel_number`.
- Filter active assessor parcels with `skagit_parcels.inactive_date IS NULL` unless historical/inactive records are explicitly required by the contract.
- Use `parcel_primary_zoning` for a single primary-zone result and `parcel_zoning` for full overlap analysis.
- Include `tax_year` in levy and tax joins whenever multiple years are possible.
- Treat Land Ledger output as generated data keyed by `(city_slug, parcel_number)` and always return `assumption_version` and `rebuilt_at`.
- Preserve raw assessor codes together with normalized descriptions in human-facing results.
- Bound large relations such as `assessor_sync_changes`, `skagit_parcel_history`, `sales`, and `improvements` by indexed filters and hard limits.
- Normalize public geometry to SRID 4326 and use controlled precision/size.

## Codex Global Execution Rules

These rules apply to every phase.

1. Read `AGENTS.md` and inspect `git status` before editing.
2. Preserve unrelated user changes and avoid unrelated refactors.
3. Work on one phase or an explicitly bounded slice of a phase at a time.
4. At the start of a phase, record the baseline evidence required by that phase.
5. Keep domain code in the owning app. MCP handlers remain thin delegates.
6. Prefer read-only inspection. Do not mutate production data, deployments, routes, credentials, or storage unless the user explicitly authorizes that exact action.
7. Never delete or retire an asset merely because it appears unused. Apply all retirement gates.
8. Do not expose `.env` values, database URLs, tokens, client secrets, OAuth codes, raw request payloads, or private graph identities in logs, fixtures, documents, or responses.
9. Do not use production parcel payloads as committed fixtures. Sanitize or synthesize fixtures.
10. Add tests with every behavior or contract change.
11. Run the narrowest relevant tests first, then the phase-level verification suite.
12. When database-backed code changes, verify referenced columns and indexes against the schema or live read-only introspection.
13. For migrations, state the forward and rollback behavior, verify them against isolated local/CI PostGIS first, and then verify the release sequence in the on-demand Railway release-candidate environment before production.
14. For public contract changes, update the registry or generator rather than hand-editing duplicated inventories.
15. Record exact verification commands, dates, target environments, and results in the phase evidence artifact.
16. If an exit gate cannot be proven, leave the phase open and report the missing evidence.
17. Stop and request direction when completion would require a new public scope, a breaking contract decision, exposure of sensitive identity data, destructive retirement, or material production cost expansion.

## Progress Tracker

| Phase | Name | Current status | Depends on |
| ---: | --- | --- | --- |
| 0 | Ownership and release target | Complete - accepted by Ian on 2026-08-01 | None |
| 1 | Local-first safe release path | Not started | Phase 0 |
| 2 | Authoritative contracts and sources | Partial | Phase 1 |
| 3 | Freshness and data quality | Partial | Phase 2 |
| 4 | Reliability and security hardening | Partial | Phases 1-3 |
| 5 | Complete verification system | Partial | Phases 2-4 |
| 6 | Missing public domains | Not started | Phases 2-5 |
| 7 | Observability, recovery, and operations | Partial | Phases 1-4; can overlap 5-6 |
| 8 | Public website and client onboarding | Not started | Phases 2, 4, and 5; can overlap 6-7 |
| 9 | Beta, adoption, and cutover | Not started | Phases 5-8 |
| 10 | Retirement and final acceptance | Blocked | Phase 9 and observation window |

## Phase 0 - Establish Ownership and Freeze the Release Target

Estimated effort: 2-3 engineering days.

### Outcome

The team has one agreed GA scope, one canonical endpoint, named decision owners, a current deployment/source baseline, and no ambiguous completion criteria.

### Deliverables

- Named accountable owners for product, MCP/platform, source data, security/privacy, and production operations.
- Frozen initial GA catalog of the existing 31 tools.
- Defined target catalog of 45 tools.
- Tool compatibility and deprecation policy.
- Current deployment, source, consumer, credential-owner, and storage inventory.
- Risk register, decision log, evidence directory, and release checklist.

### Codex goals

- [x] **GOAL 0.1 - Capture repository reality.** Enumerate the runtime registry, handlers, generated MCP tools, management commands, deployment manifests, scheduled-service manifests, documentation inventories, tests, and current git revision.
- [x] **GOAL 0.2 - Capture deployed reality.** Verify public catalog reachability, OAuth discovery, protected-resource discovery, fail-closed unauthenticated behavior, Railway services/environments/domains/replicas/health checks, and current deployment revisions.
- [x] **GOAL 0.3 - Capture data freshness.** Read only aggregate sync/run metadata for assessor, GIS, zoning, budgets, Land Ledger, tax, Census/soils, and other registered sources. Do not export parcel or identity payloads.
- [x] **GOAL 0.4 - Capture adoption.** Run the existing usage report in the supported operator environment and record calls, failures, last use, and known clients without recording secrets or request arguments.
- [x] **GOAL 0.5 - Freeze contract scope.** Produce the exact 31-tool GA-baseline list and the proposed 14-tool expansion list. Identify any existing tool that requires security, performance, or semantic review before stable status.
- [x] **GOAL 0.6 - Assign ownership.** Add named human owners or explicitly marked `TBD` blockers for each workstream and source family. Codex must not invent owner names.
- [x] **GOAL 0.7 - Resolve deployment authority.** Designate one authoritative web start lifecycle and classify `railway.json`, `Procfile`, and `railway.unified-mcp.json` as canonical, compatibility, fallback, or retired.
- [x] **GOAL 0.8 - Record open risks.** Include lack of an isolated local/CI PostGIS workflow, lack of an on-demand Railway release-candidate gate, missing smoke command, catalog drift, stale source jobs, one-replica topology, missing platform health check, Cloudflare access, and unproven client adoption.

### Required evidence

- Dated baseline report under `docs/`.
- Exact tool list generated from the Python registry.
- Railway service/environment summary.
- Source-freshness summary containing aggregate timestamps/status only.
- Consumer and retirement-candidate matrix.
- Approved compatibility policy.

### Exit gate

Every configured component is classified as deployed, not deployed, or explicitly blocked; every workstream has an owner; the 31-tool GA baseline is frozen; no deletion candidate has an unknown replacement or unexamined consumer class.

### Stop conditions

Codex must stop and request direction if the owner will not choose a canonical deployment manifest, if a currently exposed tool is judged unsafe but removal would be breaking, or if inventory requires credentials that have not been authorized.

## Phase 1 - Build a Local-First Safe Release Path

Estimated effort: 4-6 engineering days.

### Outcome

Every MCP change can be built and tested locally against the real ASGI application and an isolated PostGIS database, verified in CI, and then validated in a temporary Railway release-candidate environment before production. No permanent Railway development server is required.

### Deliverables

- Documented local ASGI development environment.
- Separate local development PostGIS database and disposable CI PostGIS strategy.
- On-demand Railway release-candidate environment that can remain stopped when unused.
- Checked-in CI workflow and pinned dependency lock.
- One authoritative ASGI deployment lifecycle.
- Separate pre-deploy/release tasks and web startup.
- Liveness/readiness endpoints and Railway health-check configuration.
- Tested release-candidate deployment and rollback procedure.

### Codex goals

- [ ] **GOAL 1.1 - Run the real application locally.** Standardize local MCP development on `python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000`, not WSGI or a transport-only mock, so `/mcp/api/`, OAuth discovery, Django, and lifespan behavior are exercised together.
- [ ] **GOAL 1.2 - Isolate local data.** Use a separate local development PostGIS database and a disposable PostGIS database in CI. Do not use SQLite and do not point ordinary development or automated tests at production.
- [ ] **GOAL 1.3 - Make local authentication safe.** Use loopback origins, dedicated local OAuth clients, development-only encryption material, console/suppressed notification delivery, local document storage, and opt-in bounded live-source calls.
- [ ] **GOAL 1.4 - Add CI.** Run Django checks, unit tests, contract snapshot checks, migrations against disposable PostGIS, formatting/linting selected by the project, dependency vulnerability scanning, secret scanning, authenticated local MCP protocol smoke, and a production-equivalent build.
- [ ] **GOAL 1.5 - Pin dependencies.** Produce a reproducible dependency lock while retaining the supported Python and MCP version policy. Add an intentional dependency-update workflow.
- [ ] **GOAL 1.6 - Consolidate startup.** Keep the public MCP on ASGI/Uvicorn. Ensure no supported deployment path silently falls back to WSGI and loses `/mcp/api/`.
- [ ] **GOAL 1.7 - Isolate release work.** Move migrations and other one-time release actions out of every web replica's normal startup. Ensure source synchronization and materialized-data rebuilds are not accidental web-boot side effects.
- [ ] **GOAL 1.8 - Add health semantics.** Implement process liveness separately from readiness. Readiness must prove database access, applied migrations, and successful MCP registry construction; it must not fail solely because an optional external source is down.
- [ ] **GOAL 1.9 - Create an on-demand Railway release candidate.** Define a separate temporary environment or service with separate OAuth credentials and notification suppression. Start it only for release validation, use sanitized/sample data or an approved protected clone strategy, and stop it when validation ends.
- [ ] **GOAL 1.10 - Configure platform health checks.** Point the release-candidate and production Railway services to readiness, set a bounded timeout, and confirm a failing candidate does not receive traffic.
- [ ] **GOAL 1.11 - Prove rollback.** In the on-demand release-candidate environment, deploy an intentionally failing candidate, confirm rejection, restore the previous working deployment, and verify database compatibility.
- [ ] **GOAL 1.12 - Validate operator commands.** Ensure documented management commands work from a clean Railway operator session without undocumented Python paths, library-path fixes, or `--skip-checks` workarounds.

### Local development standard

- Run the same ASGI entry point used in production.
- Use `http://127.0.0.1:<port>` as the local public origin and exact loopback OAuth callbacks.
- Use PostGIS for local and CI database behavior; SQLite is not an accepted substitute.
- Keep local OAuth clients, secrets, storage, email, and test data separate from production.
- Use recorded/sanitized upstream fixtures by default and bounded live checks only when the task requires current source verification.
- Make one command or documented short sequence start the local database, apply migrations, seed safe fixtures, and start ASGI.
- Make one command run the complete local contract/protocol suite.
- Keep the Railway release-candidate environment stopped or scaled to zero outside release validation when the platform supports it.

### Railway release-candidate responsibilities

The temporary Railway gate exists only to test behavior that local development cannot reliably reproduce:

- Nixpacks/build-image and native-library packaging.
- Railway variables, private networking, database connections, and service identity.
- Port binding, proxy headers, TLS origin, OAuth discovery, and callback URLs.
- Pre-deploy migration sequencing, health checks, traffic admission, and rollback.
- Production-like latency, connection limits, and multi-replica behavior where applicable.

### Required evidence

- CI run link or archived run output.
- Local setup/teardown and authenticated protocol report.
- Disposable CI PostGIS migration/test report.
- On-demand Railway release-candidate endpoint and discovery smoke report.
- Deployment-manifest decision.
- Readiness failure/success tests.
- Release-candidate rollback exercise record.
- Operator runbook verification record.

### Exit gate

A deliberately broken change is caught locally or in CI, a healthy on-demand Railway release candidate passes authenticated MCP smoke and deployment checks, and the previous release can be restored without data or credential loss.

### Stop conditions

Codex must stop if local or release-candidate setup would require copying production identity data without an approved protection strategy, if migration rollback is destructive, or if consolidating startup changes non-MCP products hosted by the same web service without their owner approval.

## Phase 2 - Make Contracts and Sources Authoritative

Estimated effort: 4-6 engineering days.

### Outcome

One versioned registry generates MCP discovery, documentation, test snapshots, limits, stability information, and source attribution. Manual tool-count and schema drift becomes a CI failure.

### Deliverables

- Extended `ToolContract` model.
- Versioned source registry and source-status storage.
- Machine-readable contract snapshot.
- Generated public/internal catalogs.
- Shared error taxonomy and protocol/envelope boundary.
- Compatibility tests.

### Codex goals

- [ ] **GOAL 2.1 - Extend tool contracts.** Add input/output schema version, stability, owner, replacement, sensitivity, maximum rows/bytes/geometry, execution deadline, pagination, cache policy, and public-use limitation fields without moving domain behavior into `openskagit_tools`.
- [ ] **GOAL 2.2 - Define source contracts.** For each stable source ID, record owner, public label, authoritative URL, coverage, attribution/license rule, authentication class, expected refresh, stale threshold, timeout, retry, cache TTL, schema fingerprint, fallback rule, and public sensitivity constraints.
- [ ] **GOAL 2.3 - Build status storage.** Store last attempt, last success, effective date, verification date, status, coverage/quality measurements, schema fingerprint, and a sanitized failure classification. Never store credentials or raw sensitive payloads.
- [ ] **GOAL 2.4 - Define error taxonomy.** Standardize at least `invalid_argument`, `not_found`, `ambiguous_match`, `source_timeout`, `source_unavailable`, `source_response_changed`, `stale_data`, `partial_result`, `rate_limited`, `response_truncated`, and `internal_error`.
- [ ] **GOAL 2.5 - Define error placement.** Authentication and JSON/schema validation remain protocol errors. Expected domain/source failures use the result envelope. Unexpected failures return a sanitized internal error plus correlation ID.
- [ ] **GOAL 2.6 - Generate artifacts.** Generate the public catalog, internal catalog, tool/source counts, and JSON snapshot from the registries. Remove manually duplicated tool tables where feasible.
- [ ] **GOAL 2.7 - Enforce consistency.** Fail CI on duplicate names/source IDs, missing handlers, unknown sources, undocumented stable tools, schema snapshot drift, or mismatched generated documentation.
- [ ] **GOAL 2.8 - Freeze compatibility rules.** Allow additive optional output fields under the current stable tool; require a new version/name and overlap window for breaking input or semantic changes.

### Required evidence

- Checked-in tool contract snapshot.
- Checked-in source catalog or migration-backed registry.
- Generated documentation diff.
- CI tests proving registry/handler/catalog/source consistency.
- Written error and compatibility policy.

### Exit gate

`tools/list`, handler registration, public documentation, internal catalog, and checked-in snapshot describe the same tools and schemas; every referenced source ID is known and owned.

### Stop conditions

Codex must stop if a compatibility decision would break an active client, if source licensing/attribution is unknown for a proposed public result, or if a source contains data whose public sensitivity has not been classified.

## Phase 3 - Operationalize Freshness and Data Quality

Estimated effort: 5-8 engineering days.

### Outcome

Every response truthfully describes the effective date, verification time, served time, coverage, and stale/partial state of its sources. Required source jobs run on documented schedules and alert on failures.

### Deliverables

- Freshness semantics and envelope revision.
- Four data-health tools.
- Scheduled GIS, Land Ledger, tax, zoning, budget, and other source verification.
- Data-quality invariants and alert thresholds.
- Source-health dashboard/operations view.

### Codex goals

- [ ] **GOAL 3.1 - Separate time semantics.** Represent `effective_at`, `verified_at`, and `served_at` distinctly. Never treat retrieval time as the data's effective date.
- [ ] **GOAL 3.2 - Define statuses.** Define precise rules for `fresh`, `stale`, `partial`, `unavailable`, and `unknown`, including how composite tools derive their overall status.
- [ ] **GOAL 3.3 - Add `data_list_sources`.** Return public source identity, coverage, expected refresh, current status, and public limitations without revealing credentials or private endpoints.
- [ ] **GOAL 3.4 - Add `data_get_source_status`.** Return latest attempt/success, effective/verified dates, quality/coverage, stale threshold, sanitized failure, and fallback state for one source.
- [ ] **GOAL 3.5 - Add `data_get_freshness`.** Return source and tool-domain freshness summaries suitable for an agent to evaluate whether a claim is current.
- [ ] **GOAL 3.6 - Add `data_get_latest_assessor_sync`.** Delegate to an `assessor_sync` read-only status service. Do not expose sync controls, raw change payloads, filesystem paths, or unrestricted per-record audit history.
- [ ] **GOAL 3.7 - Schedule missing jobs.** Establish operational schedules for GIS verification, Land Ledger rebuild, tax slow-check, zoning-corpus verification, budget coverage, and any other source required by a stable tool.
- [ ] **GOAL 3.8 - Define assessor quality thresholds.** Classify import warnings, including current land warnings, into expected/accepted versus release-blocking categories. Record counts and trends.
- [ ] **GOAL 3.9 - Define PostGIS invariants.** Test active parcel counts, parcel-to-GIS coverage, primary/full zoning coverage, duplicate keys, tax-year coverage, Land Ledger rebuild/assumption version, and delinquency check age/error rate.
- [ ] **GOAL 3.10 - Add schema-change detection.** Compare upstream and imported schema fingerprints and fail safely when required fields or parser structures change.
- [ ] **GOAL 3.11 - Alert owners.** Route stale, failed, partial, and schema-changed alerts to a named owner with runbook links.

### Required evidence

- Freshness policy by source.
- Successful scheduled-run records.
- Data-quality report with thresholds and current results.
- Representative tool responses showing fresh, stale, partial, unavailable, and unknown behavior.
- Alert delivery test.

### Exit gate

Every stable tool returns truthful freshness/provenance, every required source has a working schedule or documented live-only policy, and stale/failing sources alert a named operator.

### Stop conditions

Codex must stop before declaring a tax, delinquency, Land Ledger, zoning, or other time-sensitive tool stable if its effective date, verification policy, coverage, or scheduled refresh cannot be proven.

## Phase 4 - Reliability, Capacity, and Security Hardening

Estimated effort: 6-10 engineering days.

### Outcome

Authenticated callers cannot exhaust the service or abuse upstream sources, failures are bounded and predictable, and the deployment meets an adopted security and performance target.

### Deliverables

- Enforced per-client and global limits.
- Per-tool execution/response budgets.
- Timeout, retry, cache, circuit-breaker, and cancellation policies.
- Concurrency-model correction and load evidence.
- OAuth/security threat model and remediation.
- Privacy/logging review.

### Codex goals

- [ ] **GOAL 4.1 - Enforce argument limits.** Validate parcel IDs, years, lists, bounding boxes, geometry options, free-text lengths, jurisdictions, layer keys, and maximum limits at the public boundary and service boundary.
- [ ] **GOAL 4.2 - Enforce result limits.** Apply hard maximum rows, geometry precision/size, response bytes, and pagination. Emit `response_truncated` when safe truncation occurs.
- [ ] **GOAL 4.3 - Add client rate limits.** Carry pseudonymous OAuth client identity into request policy without putting raw credentials in logs. Enforce per-client request and concurrency limits.
- [ ] **GOAL 4.4 - Protect upstreams.** Add stricter per-source quotas for county, ArcGIS, Census, NRCS, and document sources so one client cannot amplify traffic.
- [ ] **GOAL 4.5 - Set deadlines.** Enforce source-specific connect/read timeouts and whole-tool deadlines. Retries apply only to idempotent transient failures and remain within the whole-tool deadline.
- [ ] **GOAL 4.6 - Add failure isolation.** Implement short failure caches or circuit breakers and last-known-good fallback only where provenance and policy allow it.
- [ ] **GOAL 4.7 - Support cancellation.** Stop avoidable database/upstream work when the MCP request is cancelled or disconnected.
- [ ] **GOAL 4.8 - Review thread execution.** Measure the current `thread_sensitive=True` wrapper. Keep Django ORM work safe while preventing slow pure HTTP calls from serializing unrelated requests.
- [ ] **GOAL 4.9 - Audit generic GIS query.** Constrain `gis_query_layer` to registered URLs, safe fields/operators, bounded filter complexity, and response limits. Remove or privatize it if safe public semantics cannot be proven.
- [ ] **GOAL 4.10 - Complete OAuth tests/remediation.** Verify exact redirect matching, S256 PKCE, token/client expiry, revocation, refresh rotation/replay prevention, scope enforcement, host/origin checks, and secret redaction.
- [ ] **GOAL 4.11 - Separate encryption keys.** Define a key-ring/rotation strategy for stored OAuth client secrets rather than relying on an unrotatable single `SECRET_KEY` derivation.
- [ ] **GOAL 4.12 - Review observability privacy.** Disable unnecessary default PII capture, scrub MCP/auth data from Sentry and application logs, and document the retained telemetry fields.
- [ ] **GOAL 4.13 - Test topology.** Load-test the measured replica/worker configuration. Add replicas or change worker topology when required by the SLO; do not assume a replica count without evidence.

### Initial limits to validate

These are starting values, not final policy:

- 30 calls per minute per OAuth client with a burst of 10.
- Four concurrent tool calls per client.
- 100 rows by default unless a narrower tool-specific cap is justified.
- 2 MB maximum serialized response.
- Approximately 3 seconds for internal/PostGIS tools, 10 seconds for one-upstream tools, and 25 seconds for bounded composite tools.
- At most two retries for qualifying transient failures.

### Required evidence

- Threat model and remediation checklist.
- Load-test report with p50/p95/p99, throughput, error rate, database connections, and upstream calls.
- Tests for every enforced limit.
- OAuth conformance/security test output.
- Sentry/logging redaction test.
- Adopted per-tool limits and SLO document.

### Exit gate

Limits and failure behavior are enforced, OAuth/security tests pass, sensitive data is absent from telemetry/logs, and load tests meet the adopted SLO without exhausting web, PostGIS, or upstream capacity.

### Stop conditions

Codex must stop if a required security remediation needs a breaking OAuth/client change without a migration plan, if load goals require material cost expansion without approval, or if a public generic-query contract cannot be made safe.

## Phase 5 - Build the Complete Verification System

Estimated effort: 6-9 engineering days.

### Outcome

Every public contract has automated evidence through the real MCP protocol, and deployments are continuously checked against source, auth, failure, and performance expectations.

### Deliverables

- Full golden matrix for all stable tools.
- Recorded/sanitized parser fixtures.
- Disposable PostGIS integration environment.
- Authenticated MCP end-to-end suite.
- Load/chaos suite.
- Restored unified smoke command.
- Production synthetic canary.

### Codex goals

- [ ] **GOAL 5.1 - Build the tool matrix.** For every stable tool add valid, invalid, not-found, ambiguous where applicable, empty, maximum-limit, source-timeout, partial-result, freshness, provenance, sensitive-field, and schema-snapshot cases.
- [ ] **GOAL 5.2 - Add parser fixtures.** Preserve the minimum sanitized county/ArcGIS/Census/NRCS/zoning/budget fixtures needed to detect parser and upstream schema changes.
- [ ] **GOAL 5.3 - Add PostGIS integration tests.** Use a disposable database or approved test schema with migrations, representative spatial data, tax-year cases, Land Ledger assumptions, and large-table query plans.
- [ ] **GOAL 5.4 - Verify MCP protocol.** Test `initialize`, `tools/list`, and `tools/call` through Streamable HTTP, not only direct Python handlers.
- [ ] **GOAL 5.5 - Verify authentication failures.** Test missing, invalid, expired, revoked, wrong-scope, bad-redirect, bad-PKCE, reused-code, and reused-refresh-token cases.
- [ ] **GOAL 5.6 - Verify source failures.** Simulate timeout, malformed response, schema change, upstream 4xx/5xx, partial composite failure, stale cache, and no-fallback conditions.
- [ ] **GOAL 5.7 - Verify load behavior.** Test concurrent fast/slow tools, cancellation, rate limiting, response limits, database statement timeouts, and circuit recovery.
- [ ] **GOAL 5.8 - Restore `check_unified_mcp_catalog`.** Support local/release-candidate/production targets, authenticated protocol mode, strict per-tool/whole-suite timeouts, JSON output, safe fixture identifiers, selected domains/tools, retries, and CI/monitoring exit codes.
- [ ] **GOAL 5.9 - Add a canary client.** Issue a dedicated low-privilege synthetic credential, store it through the approved secret system, call a small representative set, and alert on discovery/auth/tool failure.
- [ ] **GOAL 5.10 - Prove compatibility.** Compare legacy and canonical results for mapped tools and record intentional semantic differences.

### Required evidence

- Tool-by-tool test matrix with links to tests.
- Green local, CI, and on-demand Railway release-candidate MCP protocol runs.
- Sanitized fixture inventory.
- PostGIS integration and query-plan report.
- Load/chaos report.
- Production canary results.

### Exit gate

All 31 GA-baseline tools pass authenticated local/CI protocol tests and the on-demand Railway release-candidate gate, representative production canaries pass after deployment, and no stable contract lacks failure/limit/freshness evidence.

### Stop conditions

Codex must stop if a required fixture would contain unsanitized identity/session data, if tests can only run against the production database, or if a legacy semantic difference requires a product decision.

## Phase 6 - Add the Missing Public Domains

Estimated effort: 10-15 engineering days after Phases 2-5.

### Outcome

The singular catalog exposes the best safe, deterministic capabilities from source health, Opportunity, tax, and Land Ledger while preserving app ownership, privacy boundaries, and freshness guarantees.

### Target additions

#### Data health

1. `data_list_sources`
2. `data_get_source_status`
3. `data_get_freshness`
4. `data_get_latest_assessor_sync`

#### Opportunity

5. `opportunity_list_screen_types`
6. `opportunity_search`
7. `opportunity_get_parcel_signals`
8. `opportunity_explain_match`

#### Tax

9. `tax_get_parcel_summary`
10. `tax_get_parcel_trend`
11. `tax_get_levy_breakdown`
12. `tax_get_delinquency_status`

#### Land Ledger

13. `land_ledger_get_parcel`
14. `land_ledger_get_jurisdiction_summary`

### Codex goals

- [ ] **GOAL 6.1 - Publish data-health tools.** Promote the four Phase 3 tools only after source registry, status storage, freshness semantics, and alerts meet their exit gate.
- [ ] **GOAL 6.2 - Define Opportunity screens.** Create an explicit catalog of deterministic screens, inputs, exclusions, hard limits, source dependencies, and caveats. Do not accept arbitrary SQL or unconstrained natural language.
- [ ] **GOAL 6.3 - Implement Opportunity service boundaries.** Add public service functions inside `opportunity`, then thin MCP handlers. Exclude inactive parcels and return criteria met, missing evidence, and caveats.
- [ ] **GOAL 6.4 - Protect identity.** Remove owner mailing details, hidden entity links, and graph identity evidence from public Opportunity results. Preserve only separately approved public parcel facts.
- [ ] **GOAL 6.5 - Use screening language.** Use terms such as `screening candidate` and `signal`; never claim buildability, entitlement, legal compliance, investment quality, or guaranteed delinquency.
- [ ] **GOAL 6.6 - Implement tax services in `taxtool`.** Use canonical tax views/tables, indexed parcel joins, explicit tax years, raw plus human-readable agency fields, and reviewed methodology.
- [ ] **GOAL 6.7 - Gate delinquency freshness.** Include `source_fetched_at`/verification age, coverage, and warning/status. Do not present cached delinquency as current when its stale threshold has passed.
- [ ] **GOAL 6.8 - Implement Land Ledger services in `land_ledger`.** Return city coverage, rebuild time, assumption version, exclusions, scenario definitions, and source limitations.
- [ ] **GOAL 6.9 - Declare Land Ledger coverage.** Either expand and validate supported jurisdictions or explicitly contract the initial one-city coverage. Do not imply countywide availability from one materialized city.
- [ ] **GOAL 6.10 - Preserve PostGIS relationships.** Use canonical parcel text keys, year-qualified tax joins, primary/full zoning appropriately, and bounded/indexed access to large tables.
- [ ] **GOAL 6.11 - Complete public review.** Perform product, methodology, privacy, source-attribution, and performance review for each new tool before changing stability from beta to stable.
- [ ] **GOAL 6.12 - Reach exact catalog parity.** Generate and verify a 45-tool registry, handler set, catalog, snapshot, documentation set, and `tools/list` response.

### Deferred/private capabilities

- Arbitrary analytical SQL or public natural-language-to-SQL.
- Sync, import, rebuild, or scheduled-job controls.
- Saved-search, watchlist, preference, or notification mutations.
- Bulk parcel or geometry exports.
- Owner/entity-centric searches.
- Raw graph traversal or identity-link evidence.
- Administrative or shell access.

### Required evidence

- Approved contract and method note for each new tool.
- Golden/failure/limit/freshness tests for all additions.
- Query-plan/performance evidence for PostGIS-backed tools.
- Privacy/sensitive-field assertions.
- Local/CI, Railway release-candidate, and production canary results.
- Generated 45-tool catalog snapshot.

### Exit gate

All 45 tools meet the same contract, source, security, limit, test, and canary requirements; no added tool depends on a stale or unscheduled source; no domain behavior was moved into the faÃƒÆ’Ã‚Â§ade.

### Stop conditions

Codex must stop if an Opportunity or graph output would reveal unapproved identity relationships, if a tax/delinquency source is not current enough for the claim, if Land Ledger coverage is ambiguous, or if a proposed tool requires a new public scope or mutation authority.

## Phase 7 - Observability, Recovery, and Operations

Estimated effort: 4-6 engineering days; may overlap Phases 5-6.

### Outcome

Operators can detect incidents, identify source/tool impact, recover data and credentials, and prove service performance without storing user queries or parcel payloads.

### Deliverables

- Metrics, dashboards, and alerts.
- Synthetic monitoring.
- Retention and cleanup automation.
- Backup/restore procedure and exercise.
- Incident, source-outage, schema-change, and credential-rotation runbooks.
- Cost and capacity reporting.

### Codex goals

- [ ] **GOAL 7.1 - Extend privacy-safe telemetry.** Add pseudonymous client identity, response size, correlation ID, cache result, source timings/failure classes, rate-limit events, and freshness/coverage without arguments, parcel IDs, tokens, or payloads.
- [ ] **GOAL 7.2 - Add latency distributions.** Report p50/p95/p99 rather than only average and maximum, separated by tool, caller class, source class, and outcome.
- [ ] **GOAL 7.3 - Build dashboards.** Cover availability, latency, errors, partial results, rate limits, source health, freshness, response size, database health, and client adoption.
- [ ] **GOAL 7.4 - Configure alerts.** Alert on SLO burn, canary failure, source staleness, scheduled-job failure, schema change, database saturation, abnormal error rate, and unusual client volume.
- [ ] **GOAL 7.5 - Define retention.** Add cleanup jobs and documented retention for authorization codes, expired/revoked grants, tool telemetry, source status history, logs, fixtures, and backups.
- [ ] **GOAL 7.6 - Define RPO/RTO.** Obtain owner approval for database, OAuth, source-status, zoning/budget document, and other durable-state recovery objectives.
- [ ] **GOAL 7.7 - Verify backups.** Confirm automated PostGIS and object-storage backups, identify every mounted volume, and investigate orphaned volumes before any deletion.
- [ ] **GOAL 7.8 - Exercise restore.** Restore into an isolated environment, run migrations/checks, verify representative tool results, and record elapsed recovery time.
- [ ] **GOAL 7.9 - Exercise incidents.** Simulate an upstream outage, parser/schema change, leaked client secret, revoked client, failed deployment, and stale assessor run.
- [ ] **GOAL 7.10 - Report cost/capacity.** Track Railway compute/database/storage, Cloudflare, R2, external APIs, model use where applicable, and forecasted usage under the rate policy.

### Required evidence

- Dashboard and alert links/screenshots or configuration references.
- Successful synthetic-monitor history.
- Retention policy and cleanup-command tests.
- Backup inventory and isolated restore report.
- Incident exercise reports.
- Monthly cost/capacity baseline.

### Exit gate

An operator receives and resolves a simulated alert, a backup restores successfully within the adopted objectives, credentials can be rotated without unplanned outage, and dashboards prove current SLO/freshness state.

### Stop conditions

Codex must stop before deleting a volume/backup or rotating production credentials without explicit approval, and before setting an RPO/RTO or retention period that requires a product/legal decision.

## Phase 8 - Publish the MCP Website and Client Onboarding

Estimated effort: 3-5 engineering days; may overlap Phases 6-7 after the public contract and authentication flow are stable.

### Outcome

https://openskagit.com/mcp/ becomes the authoritative onboarding surface. It gives visitors prominent **Add to ChatGPT** and **Add to Claude** actions, explains access and OAuth requirements, and gets a user to a working connection with the fewest supported steps. If a client does not publish a stable installation link, the button opens exact in-page setup instructions rather than using an invented or reverse-engineered deep link.

### Current client-installation baseline

This client behavior is version-sensitive and must be reverified when the phase starts and immediately before release.

- [OpenAI's current ChatGPT MCP guidance](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta) documents adding remote MCP apps through ChatGPT settings and Developer Mode. The official guidance reviewed on 2026-08-01 did not identify a stable public one-click installation URL.
- [Anthropic's current remote MCP guidance](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) documents adding a remote custom connector through Claude's Connectors settings, with different owner/member steps for managed organizations. The official guidance reviewed on 2026-08-01 did not identify a stable public one-click installation URL.
- The supported baseline is therefore an instruction-backed button for each client. A true one-click link may replace that fallback only after its vendor documents and supports the link contract.
- Both hosted clients connect to the public HTTPS endpoint, not a developer's localhost server. Local MCP remains a separate development/testing path.

### Deliverables

- A responsive update to the existing Django-rendered /mcp/ page and its owned static assets.
- Two primary actions with the exact visible labels **Add to ChatGPT** and **Add to Claude**.
- A progressive installation-action contract that supports a vendor link when documented and a no-surprises instruction fallback otherwise.
- Client-specific setup panels covering eligibility, required role/admin approval, endpoint, authentication, authorization, connection enablement, and troubleshooting.
- A preserved and improved private-beta access-request path for users who need approved OAuth credentials.
- Copy controls for the endpoint and other non-secret configuration values.
- A generic remote-MCP section for other Streamable HTTP clients.
- A dated compatibility matrix linked to authoritative vendor documentation.
- Privacy-safe onboarding analytics, accessibility checks, browser tests, and production smoke evidence.

### Installation-action contract

| Action | Preferred behavior | Required fallback |
| --- | --- | --- |
| **Add to ChatGPT** | Open a vendor-documented ChatGPT installation URL only if OpenAI publishes a stable contract and the exact URL is validated in a clean account. | Open an accessible ChatGPT setup panel with current eligibility/admin notes, a copyable endpoint, OAuth credential prerequisites, exact settings steps, authorization steps, and the official help link. |
| **Add to Claude** | Open a vendor-documented Claude installation URL only if Anthropic publishes a stable contract and the exact URL is validated in a clean account. | Open an accessible Claude setup panel with individual and Team/Enterprise owner/member paths, a copyable endpoint, OAuth credential prerequisites, connection-enablement steps, and the official help link. |

A fallback action may still carry the visible **Add to ...** label, but it must immediately identify itself as setup instructions. It must never pretend that a connector was installed.

### Codex goals

- [ ] **GOAL 8.1 - Inventory the existing page.** Inspect openskagit_tools/templates/openskagit_tools/catalog.html, its view/form context, static/mcp.css, JavaScript, URL routing, access-request storage/notification behavior, and tests. Preserve the working catalog and request-access workflow while removing stale copy.
- [ ] **GOAL 8.2 - Reverify official client support.** At implementation and release time, use official OpenAI and Anthropic documentation to record supported plans, surfaces, organization roles, remote-connector requirements, OAuth behavior, callback requirements, and whether a documented installation link exists. Store a visible Last verified date and source links; do not rely on remembered UI labels.
- [ ] **GOAL 8.3 - Implement honest add-button routing.** Add the two required buttons through configuration-backed targets. Use only documented HTTPS vendor URLs. When a supported install target is absent, route to an in-page dialog or anchored section with Setup instructions state text. Never scrape a private URL, automate a logged-in client UI, or construct an undocumented deep link.
- [ ] **GOAL 8.4 - Publish the ChatGPT path.** Explain the currently supported Developer Mode/custom-app workflow, plan/workspace eligibility, admin approval where applicable, remote endpoint entry, OAuth selection and approved client credentials, tool scan/review, authorization, and enabling the app. Link to the official OpenAI guidance and label beta or plan limitations with the verification date.
- [ ] **GOAL 8.5 - Publish the Claude path.** Explain the current individual and managed-organization connector workflows, remote endpoint entry, Advanced OAuth client settings when required, per-user authorization, and enabling the connector for a conversation. Link to the official Anthropic guidance and label beta, plan, role, and network limitations with the verification date.
- [ ] **GOAL 8.6 - Integrate access safely.** Give each setup panel clear I have credentials and Request access paths. Reuse the existing CSRF-protected form, preserve manual approval and revocation, never embed or prefill a client secret, never expose another user's client ID, and explain that credentials are delivered through the approved channel.
- [ ] **GOAL 8.7 - Document generic remote-MCP configuration.** Publish the canonical endpoint https://openskagit.com/mcp/api/, transport, OAuth metadata/discovery locations, required read scope, public catalog link, and troubleshooting guidance without publishing secrets or unsupported client-specific config.
- [ ] **GOAL 8.8 - Make compatibility explicit.** Add a compact matrix for ChatGPT, Claude web/Desktop, and generic remote clients showing tested status, plan/role constraints, authentication mode, setup type (direct link or instructions), last verification date, and known limitations. Do not claim support based only on protocol similarity.
- [ ] **GOAL 8.9 - Meet accessibility and progressive-enhancement requirements.** Ensure both actions and dialogs work with keyboard and screen readers, manage focus correctly, meet contrast/touch-target requirements, render on mobile, retain usable instructions without JavaScript, and provide a copy fallback when the Clipboard API is unavailable.
- [ ] **GOAL 8.10 - Instrument the onboarding funnel privately.** Record button client, action mode (vendor_link or instructions), access-request transition, and success/help events without endpoint credentials, OAuth codes, client IDs, emails, intended-use text, or full URLs containing sensitive query data. Define retention and an opt-out-aware analytics policy.
- [ ] **GOAL 8.11 - Add automated and visual verification.** Add Django view/template tests, exact-label and link-policy tests, no-secret assertions, form-regression tests, JavaScript/copy fallback tests, accessibility checks, link validation, and desktop/mobile browser screenshots. Test instruction mode unconditionally and vendor-link mode behind explicit configuration.
- [ ] **GOAL 8.12 - Deploy and smoke the public flow.** Promote through the standard release path, confirm /mcp/ returns 200, verify both buttons and their fallbacks from a clean browser, submit a synthetic access request without triggering unintended notifications, and complete approved ChatGPT and Claude connection attempts when suitable test accounts are available.
- [ ] **GOAL 8.13 - Treat directories as a later distribution channel.** Evaluate official ChatGPT app-directory and Anthropic Connectors Directory submission only after the endpoint, privacy policy, support process, branding, security review, and catalog stability satisfy each vendor's current requirements. Directory acceptance is not required to ship the instruction-backed buttons.

### Required evidence

- Before/after desktop and mobile screenshots of /mcp/.
- Dated ChatGPT and Claude compatibility matrix with authoritative source links.
- Recorded decision for each button: documented vendor link or instruction fallback.
- Passing view, template, form, accessibility, browser, copy-control, link-policy, and no-secret tests.
- Clean-browser verification that both actions are understandable and reversible.
- Successful approved reference connections, or a recorded external-account/admin blocker that leaves truthful tested instructions in place.
- Production 200/readiness result and privacy-safe onboarding event evidence.

### Exit gate

The public page shows both required actions prominently; each action either uses a currently documented and tested vendor installation contract or opens complete setup instructions; users can copy the endpoint, determine eligibility, request credentials, authorize the connector, and find troubleshooting/support; no secrets or unsupported compatibility claims are exposed; and the page passes desktop, mobile, keyboard, screen-reader, form-regression, and production smoke checks.

### Stop conditions

Codex must stop before publishing an undocumented install URL, automating a user's authenticated ChatGPT/Claude settings, weakening OAuth to make onboarding easier, embedding shared credentials, exposing submitted access-request data, claiming support for an untested plan/client, sending test notifications to real recipients, or submitting to a vendor directory without explicit owner authorization.

## Phase 9 - Beta, Adoption, and Cutover

Estimated effort: 4-6 engineering days plus observation time.

### Outcome

Real approved clients use the canonical MCP successfully, known legacy consumers have migration paths, and traffic evidence supports beginning the final retirement window.

### Deliverables

- Reference-client onboarding and evidence.
- Public quickstart, limits, status, changelog, and migration guide.
- Legacy/canonical parity report.
- Cloudflare/Railway deployment and traffic inventory.
- D1/R2 backups and consumer map.
- Started 30-day zero-legacy-traffic observation window.

### Codex goals

- [ ] **GOAL 9.1 - Validate onboarding.** Complete the public-page workflow and documented OAuth flow with approved ChatGPT and Claude test accounts, then verify one generic remote-MCP client if the compatibility matrix claims generic support.
- [ ] **GOAL 9.2 - Exercise real workflows.** Run representative parcel, GIS, context, zoning, budget, Opportunity, tax, Land Ledger, and data-health requests and collect consented usability/reliability feedback.
- [ ] **GOAL 9.3 - Publish operator/user documentation.** Document endpoint, authentication, supported clients, tool discovery, limits, pagination, freshness, errors, responsible use, attribution, support, and status reporting.
- [ ] **GOAL 9.4 - Publish compatibility mapping.** Map every legacy tool/endpoint to the canonical replacement or intentional discontinuation, including semantic differences.
- [ ] **GOAL 9.5 - Identify consumers.** Use Railway, OAuth, MCP telemetry, Cloudflare, repository configuration, and owner interviews to identify external and internal callers. Do not infer zero consumers solely from source-code search.
- [ ] **GOAL 9.6 - Restore Cloudflare visibility.** Obtain authorized account access and export deployed versions, routes/domains, cron triggers, traffic analytics, D1 inventory/counts, R2 inventory, bindings, and secret names.
- [ ] **GOAL 9.7 - Preserve legacy state.** Export and validate required D1/R2 data and minimum sanitized fixtures before freezes or shutdowns.
- [ ] **GOAL 9.8 - Migrate clients.** Deliver dates, endpoint/tool mappings, credential instructions, and support path to known clients; verify successful canonical calls.
- [ ] **GOAL 9.9 - Freeze legacy evolution.** Permit only critical security/availability fixes during the observation window.
- [ ] **GOAL 9.10 - Start the evidence clock.** Begin the 30-day zero-traffic window only after known consumers move and traffic measurement is trustworthy.

### Required evidence

- Successful reference-client session records without secrets/payloads.
- Current onboarding and migration documentation.
- Legacy/canonical parity report.
- Authenticated Cloudflare inventory export summary.
- D1/R2 backup verification.
- Dated observation-window start and traffic dashboard.

### Exit gate

Approved ChatGPT and Claude reference clients use the canonical MCP through the public onboarding workflow, any advertised generic-client support has been verified, known consumers have migrated or been intentionally discontinued, SLOs hold under real use, legacy traffic measurement is trustworthy, and the required zero-traffic window has completed.

### Stop conditions

Codex must stop if a known consumer has no approved migration/discontinuation decision, if Cloudflare traffic cannot be measured, if backup verification fails, or if beta usage exposes a material security, freshness, or contract problem.

## Phase 10 - Retire Legacy Infrastructure and Accept Production

Estimated effort: 2-4 engineering days after the observation window.

### Outcome

OpenSkagit has one supported production MCP interface, legacy components and credentials are safely retired, rollback windows expire successfully, and product/data/security/operations owners sign final acceptance.

### Retirement gates

Every component must satisfy all of these before destructive action:

- Replacement is identified and tested.
- Consumers moved or were intentionally discontinued.
- Production traffic is zero for the approved observation window.
- Unique data is migrated, backed up, or approved for destruction.
- Routes, crons, queues, bindings, domains, and environment references are identified.
- Component-only secrets/tokens are identified.
- Rollback procedure and window are documented.
- Owner approval is recorded.

### Codex goals

- [ ] **GOAL 10.1 - Build a per-component retirement packet.** Include replacement, parity evidence, consumers, traffic, data disposition, backup, infrastructure references, credentials, rollback, and approver.
- [ ] **GOAL 10.2 - Retire in dependency order.** Remove consumers first, then routes/schedules/bindings, then stop deployment, then revoke credentials, then consider source/local deletion after the rollback window.
- [ ] **GOAL 10.3 - Protect the canonical domain.** Never remove or change the Cloudflare DNS/proxy for `openskagit.com` merely because standalone Workers are being retired.
- [ ] **GOAL 10.4 - Smoke after every shutdown.** Verify public catalog, discovery, fail-closed auth, authenticated `initialize`, exact `tools/list`, representative calls, source health, and web products after each component is stopped.
- [ ] **GOAL 10.5 - Preserve rollback.** Keep the documented rollback artifact/backup for the approved window and verify it remains usable.
- [ ] **GOAL 10.6 - Revoke credentials last.** Revoke component-only secrets after the replacement is verified and rollback implications are understood. Rotate shared credentials rather than deleting them blindly.
- [ ] **GOAL 10.7 - Remove source only with approval.** Do not delete local projects, Worker source, D1/R2 data, volumes, or fixtures without explicit owner approval recorded in the deprecation register.
- [ ] **GOAL 10.8 - Reconcile all inventories.** Update the platform catalog, deployment inventory, source catalog, public MCP docs, deprecation register, and credential/backup records.
- [ ] **GOAL 10.9 - Run final acceptance.** Execute the complete release, protocol, contract, load, security, canary, backup, restore, and incident evidence review.
- [ ] **GOAL 10.10 - Obtain signoff.** Record product, data/methodology, security/privacy, and operations approval. Codex may prepare the record but must not impersonate or invent human approval.

### Required evidence

- Completed retirement packet for every removed component.
- Post-shutdown smoke/canary results.
- Credential revocation/rotation record without secret values.
- Backup and rollback-window record.
- Updated catalog/register/inventory.
- Signed final acceptance record.

### Exit gate

One documented endpoint exposes the supported catalog; legacy traffic is zero; redundant deployments, routes, schedules, bindings, stores, and component-only credentials are retired or explicitly retained with justification; rollback windows have expired; final owners have signed acceptance.

### Stop conditions

Codex must stop before every destructive retirement action unless its exact target, evidence packet, backup, rollback, and owner approval are verified. Ambiguous service, route, volume, bucket, database, or credential identity is an automatic stop.

## Production Service-Level Objectives

The owners must approve final values after load testing. Initial targets:

| Measure | Initial target |
| --- | --- |
| MCP endpoint availability | 99.5% monthly or better |
| Internal/PostGIS tool p95 | Under 2 seconds where query class supports it |
| Single-upstream tool p95 | Under 8 seconds |
| Bounded multi-source/overlay tool p95 | Under 20 seconds |
| Unauthorized successful calls | Zero |
| Stable tool schema drift | Zero unreviewed breaking changes |
| Critical source stale without alert | Zero |
| Production release without local/CI and Railway release-candidate evidence | Zero |
| Recovery test frequency | At least quarterly after initial restore exercise |

SLO exclusions and maintenance windows must be explicit; they must not be invented after an incident to improve reported compliance.

## Final Definition of Done

- [ ] One canonical HTTPS Streamable HTTP endpoint is documented and supported.
- [ ] OAuth discovery, S256 PKCE, refresh rotation, revocation, client expiry, and scope enforcement are proven in production.
- [ ] Registry, handlers, generated docs, snapshots, and `tools/list` contain identical tools.
- [ ] All 45 intended public tools are read-only, bounded, versioned, owned, and covered by authenticated protocol tests.
- [ ] Every tool returns structured provenance, coverage, freshness, warnings, and errors.
- [ ] All list/search tools enforce limits and pagination where applicable.
- [ ] No public tool exposes unrestricted SQL, sync/import/rebuild controls, private user mutations, administrative actions, or protected graph identities.
- [ ] Local ASGI/PostGIS development, disposable CI PostGIS, an on-demand Railway release-candidate gate, dependency locking, readiness checks, safe release tasks, and rollback are operational.
- [ ] Deployed topology meets the adopted SLO under load.
- [ ] Per-client and per-source rate/concurrency limits are enforced.
- [ ] Source failures, schema changes, job failures, and staleness alert named owners.
- [ ] Privacy-safe dashboards show usage, p50/p95/p99 latency, errors, response size, source status, and adoption.
- [ ] PostGIS/object-storage backups and an isolated restore have been verified.
- [ ] OAuth and upstream credentials have tested rotation/revocation procedures.
- [ ] The public **/mcp/** page has prominent **Add to ChatGPT** and **Add to Claude** actions, copyable non-secret configuration, access-request routing, and current official documentation links.
- [ ] Each client action uses a vendor-documented, tested installation contract or clearly opens complete manual setup instructions; no undocumented deep link or shared credential is published.
- [ ] Reference ChatGPT and Claude clients complete real sessions through the canonical endpoint, or any vendor-account/admin blocker is explicitly recorded without overstating support.
- [ ] Known legacy consumers migrate or receive approved discontinuation decisions.
- [ ] Legacy endpoints complete the required zero-traffic window.
- [ ] Unique D1/R2/legacy state is backed up, migrated, or approved for destruction.
- [ ] Redundant routes, schedules, bindings, deployments, and component-only credentials are removed.
- [ ] Runbooks have been exercised, not merely written.
- [ ] Product, data/methodology, security/privacy, and operations owners sign final acceptance.

## Critical Path and Schedule

Critical path:

```text
Phase 0 baseline/ownership
    -> Phase 1 local-first development/release safety
    -> Phase 2 contracts/source registry
    -> Phase 3 freshness/jobs
    -> Phases 4 and 5 hardening/verification
    -> Phase 6 catalog expansion
    -> Phase 8 public onboarding
    -> Phase 9 beta/cutover
    -> 30-day observation
    -> Phase 10 retirement/acceptance

Phase 7 observability/recovery begins after Phase 1 and runs alongside Phases 3-6. Phase 8 page work may begin once the contract and auth flow are stable, but it must pass the Phase 5 verification and Phase 7 operational gates before public beta onboarding.
```

Estimated delivery:

- One experienced engineer: approximately 13-17 weeks.
- Two engineers with active domain-owner support: approximately 8-11 weeks to GA.
- Legacy retirement includes a 30-day observation period, which may overlap beta.
- Re-estimate after Phase 0 once ownership, local/CI database setup, release-candidate scope, source coverage, and contract-review scope are known.

## Immediate Execution Slice

The first implementation milestone is **Local Development + Release Safety + Source Truth**.

Codex should execute these tasks before adding Opportunity, tax, or Land Ledger tools:

1. Complete Phase 0 evidence and ownership gaps.
2. Standardize local ASGI development with a separate local PostGIS database.
3. Add CI with disposable PostGIS.
4. Define an on-demand Railway release-candidate environment that remains stopped when unused.
5. Consolidate ASGI deployment/startup configuration.
6. Add real readiness and configure Railway health checks.
7. Restore the 31-tool unified authenticated smoke command.
8. Add the authoritative source registry/status model.
9. Schedule and verify GIS, Land Ledger, and tax refresh jobs.
10. Generate the catalog from the registry and eliminate the current 25-versus-31 documentation drift.
11. Restore authorized Cloudflare inventory access.
12. Run release-candidate rollback and operator-runbook exercises.

## Phase Evidence Template

Codex should add or update an evidence record for each phase using this structure:

```markdown
# Phase N Evidence - <name>

Date:
Codex session/commit:
Environment(s):
Human owner(s):

## Goals completed
- GOAL N.1: complete/incomplete - evidence

## Changes
- Files/migrations/deployments changed

## Verification
- Command or protocol check
- Target environment
- Result

## Security and data review
- Secrets/PII handling
- Source/freshness impact
- Compatibility impact

## Open risks
- Risk, owner, next action

## Exit gate
- Passed/not passed
- Human approval where required
```

## Steady-State Governance After Acceptance

- Review catalog, source registry, access clients, dependencies, limits, and usage quarterly.
- Test backup restoration and credential rotation quarterly.
- Review source licensing, coverage, freshness thresholds, and data-quality invariants at least annually and whenever a source changes.
- Require contract snapshot and generated documentation updates in every public-tool pull request.
- Reverify ChatGPT and Claude onboarding guidance, compatibility claims, and add-button targets quarterly and before every material client-onboarding release; automatically fail safe to instructions if a vendor link is removed or becomes unverified.
- Deprecate unused tools only with usage evidence and the compatibility policy.
- Treat a new source, public scope, mutation tool, bulk export, or identity-oriented capability as a new reviewed project rather than an incidental handler addition.
