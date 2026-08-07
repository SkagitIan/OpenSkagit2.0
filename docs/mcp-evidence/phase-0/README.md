# Phase 0 Evidence - Ownership and Release Target

Date: 2026-08-01  
Inspection completed: 2026-08-01T18:23:57Z  
Codex session/commit: working tree at `b2a4de6bc96bdffa68306bea91163dc1973e881f`  
Environment(s): local repository and Railway `production`  
Human owner(s): Ian (all accountable roles); see [governance.md](governance.md)

## Outcome

Phase 0 repository, public-boundary, Railway, source-freshness, catalog, adoption,
consumer, storage, and risk evidence has been captured. The initial GA baseline is
frozen at the 31 read-only tools in the runtime registry, and the target expansion
is frozen at the 14 tools listed in the production plan.

The Phase 0 exit gate **passed on 2026-08-01**. Ian accepted all accountable
human roles and approved the compatibility policy, including a 90-day minimum
overlap for a breaking stable-tool replacement.

Cloudflare account inventory remains explicitly blocked by missing Wrangler
authentication. This does not prevent Phase 1 local work, but it blocks any
retirement or claim that Cloudflare consumers and assets are fully known.

## Goals completed

- GOAL 0.1: complete - repository revision, registry, handlers, generated MCP
  parity, commands, manifests, tests, CI, and dependency state are recorded in
  [repository-and-deployment.md](repository-and-deployment.md).
- GOAL 0.2: complete with an explicit Cloudflare blocker - public catalog and
  OAuth probes and Railway topology are recorded in
  [repository-and-deployment.md](repository-and-deployment.md) and
  [consumers-and-retirement.md](consumers-and-retirement.md).
- GOAL 0.3: complete - aggregate-only source state is recorded in
  [source-freshness.md](source-freshness.md).
- GOAL 0.4: complete - the supported operator usage report and sanitized OAuth
  aggregate are recorded in [consumers-and-retirement.md](consumers-and-retirement.md).
- GOAL 0.5: complete - the exact 31-tool baseline, 14-tool expansion, and review
  flags are recorded in [tool-catalog.md](tool-catalog.md).
- GOAL 0.6: complete - Ian accepted ownership of every required workstream,
  source family, credential class, and production operations role.
- GOAL 0.7: complete - `railway.json` is canonical, `Procfile` is compatibility-
  only, and `railway.unified-mcp.json` is an undeployed fallback. The production
  plan supersedes the former startup rule.
- GOAL 0.8: complete - open risks and next actions are recorded in
  [governance.md](governance.md).

## Changes

- Added this Phase 0 evidence directory.
- Updated `AGENTS.md` to record the user-approved deployment authority and remove
  the conflict between the repository rule and the production plan.
- No application code, database data, Railway service, Cloudflare asset,
  credential, route, schedule, storage object, or production deployment changed.

## Verification

| Check | Target | Result |
| --- | --- | --- |
| `git rev-parse HEAD` | local | `b2a4de6bc96bdffa68306bea91163dc1973e881f` |
| `python manage.py test openskagit_tools --verbosity 2` | local, no DB created | 24/24 passed; Django checks passed |
| Runtime registry extraction | local Python registry | 31 unique version `1.0` read-only contracts |
| Registry/handler/FastMCP parity | local tests | exact parity passed |
| `GET /mcp/` | production | 200; advertises 31 read-only tools |
| OAuth authorization metadata | production | 200; authorization code, refresh token, revocation, S256, `openskagit.read` |
| OAuth protected-resource metadata | production | 200; canonical resource and bearer header advertised |
| Unauthenticated MCP `initialize` | production | 401 JSON; fail-closed boundary confirmed |
| `railway status --json` | Railway production | one environment, five services, two volumes |
| `report_mcp_usage --days 30` | Railway operator environment | three controlled calls, zero failures, no external adoption evidence |
| Read-only aggregate freshness query | configured PostGIS | completed; no parcel, owner, request, identity, or raw payload exported |
| `npx wrangler whoami` | Cloudflare | blocked: not logged in / HTTP 400 token failure |

## Security and data review

- No secrets, database URLs, tokens, OAuth codes, client IDs, client secrets,
  request arguments, parcel identifiers, owner identities, or production payloads
  are recorded in these artifacts.
- OAuth evidence is limited to aggregate counts, client class labels, and dates.
- Database evidence is limited to counts, statuses, coverage, and timestamps.
- Cloudflare inspection stopped at the authentication boundary; no workaround or
  mutation was attempted.

## Open risks

The authoritative register is [governance.md](governance.md). The highest current
risks are the production-only release path, no checked-in CI or dependency lock,
one web replica without a health check, startup-time migrations/source work,
stale or unscheduled source jobs, generic GIS query exposure, unknown Cloudflare
traffic and assets, and no demonstrated client adoption.

## Exit gate

**Passed on 2026-08-01.** Configured components are classified as deployed, not
deployed, source-only, or explicitly blocked; the 31-tool baseline is frozen;
Ian owns all accountable roles; and the compatibility policy is approved. This
approval closes Phase 0 only and does not authorize destructive work.
