# OpenSkagit Platform Consolidation Plan

Status: active
Date: 2026-07-15
Execution home: `OpenSkagit-railway`

## Execution Progress

- 2026-07-15: created `openskagit_tools` with a versioned contract registry and common result envelope.
- 2026-07-15: published 22 read-only parcel, GIS, and zoning tools through one stdio MCP façade.
- 2026-07-15: retained the three domain MCPs as compatibility bridges.
- 2026-07-15: initially blocked remote transport until required authentication was implemented.
- 2026-07-15: added opt-in streamable HTTP with fail-closed bearer authentication, read scope enforcement, HTTPS validation, and a separate Railway service configuration.
- 2026-07-15: verified unit contracts, domain-service delegation, Django checks, and MCP initialize/tool discovery.
- 2026-07-15: added the public registry-backed catalog and reviewed access-request workflow at `/mcp/`.
- 2026-07-15: integrated the canonical `/mcp/api/` endpoint, OAuth discovery, PKCE authorization, encrypted client credentials, and revocable grants into the Django ASGI deployment.
- 2026-07-15: verified desktop/mobile browser behavior, form validation, OAuth discovery, and fail-closed unauthenticated MCP access.

## Objective

Deliver one coherent OpenSkagit civic/property intelligence platform with a single supported tool catalog, one canonical PostGIS store, explicit security boundaries, and no redundant deployed projects.

The product should feel like one large toolset without becoming one large implementation file. Domain services remain modular; discovery, authentication, contracts, provenance, and deployment ownership are consolidated.

## Goals And Success Measures

### Goal 1: One canonical platform

Make `OpenSkagit-railway` the only actively developed application repository for the current product.

Success measures:

- Every supported feature has one owner in `platform-catalog.md`.
- Older `OpenSkagit` and top-level `mcp` receive no production features after migration starts.
- New parcel, GIS, zoning, tax, and opportunity work uses Railway services and PostGIS.

### Goal 2: One discoverable tool interface

Expose assessor, GIS, zoning, context, opportunity, and freshness tools through one authenticated MCP façade.

Success measures:

- One production endpoint publishes the supported read-only catalog.
- Existing assessor, GIS, and zoning services are reused rather than copied.
- Three separate domain MCP processes can be disabled without capability loss.
- Ask Agent uses same-process services inside Railway and MCP across process boundaries.

### Goal 3: One authoritative analytical store

Use Railway PostgreSQL/PostGIS as the system of record and eliminate the full parcel duplicate in D1.

Success measures:

- Every supported parcel/opportunity query has a PostGIS implementation.
- D1/PostGIS parity is measured on a golden dataset before cutover.
- No production consumer reads or writes the D1 parcel store for 30 days before deletion.
- A backup and restoration note exist before D1 removal.

### Goal 4: Secure operational boundaries

Separate public reads, authenticated user mutations, background jobs, and privileged administration.

Success measures:

- Production MCP requires authentication and validates tools and arguments.
- Django `manage` and `shell` remain local/admin-only.
- Calls record tool, duration, outcome, freshness, and caller class without secrets.
- Notifications, saved-search mutations, and syncs require explicit scopes.

### Goal 5: Remove redundant projects

Delete components whose behavior, data, and traffic have moved to a canonical replacement.

Success measures:

- Every retirement passes `deprecation-register.md` gates.
- Duplicate Worker names, D1 bindings, registries, and assessor parsers are eliminated.
- Retired routes, schedules, tokens, and secrets are removed.
- Local directories are archived only when needed; otherwise deleted after approval.

### Goal 6: Keep the catalog true

Treat architecture and inventory as maintained product artifacts.

Success measures:

- Catalog updates are part of done for tool/deployment changes.
- Source health reports last verification, successful sync, and stale/failed status.
- Golden contract tests cover every public tool.

## Target Decisions

1. `OpenSkagit-railway` is canonical.
2. PostgreSQL/PostGIS is canonical for parcel and analytical data.
3. `assessor_mcp`, `gis_mcp`, and `zoning_mcp` remain domain implementations.
4. New `openskagit_tools` owns MCP transport, schemas, authentication, common envelopes, and registration.
5. Generic Django MCP remains separate local administrator tooling.
6. Workers remain only for demonstrated edge or notification benefits.
7. The D1 parcel pipeline freezes once deployment and traffic are known.

## Workstreams

### Contracts and catalog

- Freeze names, inputs, outputs, errors, provenance, and warnings.
- Add the common result envelope in `platform-catalog.md`.
- Define compatibility rules for renamed tools.
- Build golden cases for valid, missing, ambiguous, multi-zone, geometry-free, and source-failure behavior.

### Unified MCP façade

- Create `openskagit_tools` in Railway.
- Register thin wrappers around domain services.
- Support authenticated HTTP MCP externally and stdio locally only if useful.
- Add request limits, timeouts, structured errors, and audit events.
- Keep domain logic out of transport wrappers.

### Service convergence

- Move unique Census and SSURGO behavior from `OpenSkagit/worker` to a context service.
- Compare Cloudflare property parsing with `assessor_mcp.services`; retain one parser per source page.
- Make Ask Agent call local services when co-located.
- Continue Opportunity's direct zoning-service use.
- Consolidate GIS/source definitions and verification into one registry.

### Data convergence

- Inventory D1 tables, counts, last ingest, consumers, and traffic.
- Map D1 fields to PostGIS and resolve unique fields explicitly.
- Run sampled and aggregate parity reports.
- Switch consumers, freeze D1 writes, observe, back up, then remove.

### Deployment and security cleanup

- Authenticate to Cloudflare/Railway and record deployed reality.
- Map routes, crons, bindings, domains, variables, and token ownership.
- Require production MCP authentication.
- Remove consumers and routes before deployments.
- Revoke credentials associated only with retired components.

### Deprecation and deletion

- Announce deprecation and freeze new features.
- Remove runtime dependencies before source deletion.
- Apply the register's gates.
- Delete local projects only after owner approval of final `DELETE` state.

## Phases

### Phase 0: Verify reality

Deliver:

- Authenticated Cloudflare Worker, route, D1, R2, cron, secret-name, and traffic inventory.
- Railway service/cron inventory.
- Consumer map for every endpoint/database.
- Baseline contract tests against the current MCP.

Exit when every configured deployment is `deployed`, `not deployed`, or explicitly blocking, and no deletion candidate has an unknown consumer.

### Phase 1: Freeze and protect

Deliver:

- Versioned tool schemas and common envelope.
- Required production MCP authentication.
- Deprecation notices on duplicate projects.
- D1 feature freeze.

Exit when existing behavior is reproducible by tests and privileged Django tools are excluded from public transport.

### Phase 2: Build unified façade

Deliver:

- One MCP catalog for parcel, GIS, zoning, Census/soils, opportunity, and freshness.
- Same-process integration for Ask Agent and Opportunity.
- Structured audit, error, and latency logging.

Exit when all public tools pass golden tests and normalized outputs shadow the old endpoint successfully.

### Phase 3: Consolidate sources and data

Deliver:

- One source registry.
- Census/soils and other unique Worker behavior migrated.
- D1/PostGIS parity report and consumer cutover.

Exit when no required capability lives only in a retirement candidate and D1 has no readers/writers for 30 days.

### Phase 4: Retire infrastructure

Deliver:

- Remove duplicate Workers, routes, crons, D1/R2 bindings, and secrets.
- Remove separate domain MCP configs after compatibility period.
- Archive or delete old projects per the approved register.

Exit when smoke tests pass after shutdown, rollback windows expire, and the catalog contains only justified components.

### Phase 5: Tighten operations

Deliver:

- Freshness dashboard and alerts.
- Tool usage/latency/error review.
- Quarterly catalog and dependency review.
- Railway, Cloudflare, storage, and model cost report.

Exit when stale/failing sources alert an owner and unused tools are identifiable from telemetry.

## Retirement Gates

A component may be deleted only when all apply:

- Replacement is identified and tested.
- Consumers moved or were intentionally discontinued.
- Production traffic is zero for the observation window.
- Unique data is migrated, backed up, or approved for destruction.
- Routes, crons, queues, bindings, domains, and environment references are removed.
- Component-only secrets/tokens are revoked.
- Rollback procedure/window is documented.
- Project owner approves deletion.

## Immediate Next Actions

1. Log into Cloudflare or supply a read-only token and complete Phase 0.
2. Decide whether external MCP runs on Railway or as a thin Cloudflare gateway backed by Railway.
3. Add contract tests for seven Cloudflare tools and local assessor/GIS/zoning tools.
4. Implement common envelopes and unified registration.
5. Freeze `cloudflared`, `skagit-pipeline`, and top-level `mcp` pending parity.
6. Approve preliminary dispositions before destructive cleanup.

## Definition Of Done

One documented, authenticated gateway exposes supported tools; PostGIS is the only full analytical parcel store; every job and Worker has one reason to exist; old projects and credentials are removed; and the catalog matches production reality.
