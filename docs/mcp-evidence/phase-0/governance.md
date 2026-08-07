# Phase 0 Governance, Decisions, and Risk Register

Date: 2026-08-01

## Accountable ownership

Ian explicitly accepted every accountable human role on 2026-08-01. One person
therefore owns product/GA scope, MCP/platform engineering, source data and
methodology, security/privacy, production operations, source families, and
credential classes.

| Workstream | Accountable human | Required responsibilities | Gate status |
| --- | --- | --- | --- |
| Product/GA scope | Ian | stable catalog, compatibility, beta/adoption, discontinuation decisions | accepted 2026-08-01 |
| MCP/platform engineering | Ian | registry, transport, OAuth, releases, limits, protocol tests | accepted 2026-08-01 |
| Source data/methodology | Ian | assessor/GIS/zoning/budget/tax/Land Ledger coverage, warnings, attribution | accepted 2026-08-01 |
| Security/privacy | Ian | scopes, client approval, sensitive fields, logging, threat model, incidents | accepted 2026-08-01 |
| Production operations | Ian | Railway/Cloudflare ownership, alerts, backups, restore, credentials, SLO | accepted 2026-08-01 |

### Source-family operator assignment

| Source family | Owning application | Human owner | Current operating state |
| --- | --- | --- | --- |
| PostGIS/parcel search | `assessor_mcp` plus platform DB | Ian | canonical store; daily assessor feed |
| Property OneStop live parcel | `assessor_mcp` | Ian | live-only, no durable source status |
| Assessor bulk/auditor | `assessor_sync` | Ian | deployed daily job |
| GIS registry/ArcGIS | `gis_mcp` | Ian | live registry plus overdue local downloads |
| Census/soils | `context_mcp` | Ian | live-only, no scheduled verification |
| Zoning corpus | `zoning_mcp` | Ian | last imported 2026-06-30; no verifier job |
| Public budgets | `budgets` | Ian | reviewed records; no verifier job |
| Opportunity | `opportunity` | Ian | not public in MCP baseline |
| Parcel tax | `taxtool` | Ian | not public in MCP baseline |
| Delinquency | `tax_delinquency` | Ian | latest source fetch 2026-06-26; no active job |
| Land Ledger | `land_ledger` | Ian | Sedro-Woolley only; no rebuild job |
| Cloudflare legacy assets | retirement program | Ian | account inventory blocked |

## Decision log

| ID | Date | Decision | Authority/evidence | Consequence |
| --- | --- | --- | --- | --- |
| D-001 | 2026-08-01 | `OpenSkagit-railway` is the canonical repository, `https://openskagit.com/mcp/api/` the canonical endpoint, and Railway PostGIS the canonical analytical store. | production plan plus successful production probes | New public work targets this control plane. |
| D-002 | 2026-08-01 | Freeze the existing 31 registry tools as the initial GA compatibility baseline and the named 14 additions as target scope. | production plan and runtime registry extraction | Silent removal/rename/semantic change is prohibited. |
| D-003 | 2026-08-01 | The production plan supersedes the former repository rule requiring migrations in web startup. | explicit user instruction | Phase 1 will isolate release tasks after local/CI/release-candidate proof. |
| D-004 | 2026-08-01 | `railway.json` is canonical; `Procfile` is compatibility-only; `railway.unified-mcp.json` is an undeployed fallback. | deployed Railway manifest and ASGI/WSGI route behavior | No supported path may silently move the public MCP to WSGI. |
| D-005 | 2026-08-01 | Phase 0 is read-only toward production and authorizes no retirement. | production plan safety rules | All deletion, shutdown, route, secret, and storage gates remain closed. |
| D-006 | 2026-08-01 | Treat `check_unified_mcp_catalog` as present but incomplete, not absent. | tracked command inspection | Phase 5 extends it to authenticated protocol/environment coverage. |
| D-007 | 2026-08-01 | Cloudflare inventory is explicitly blocked rather than inferred from source configuration. | `wrangler whoami` not authenticated | No Worker/D1/R2 retirement or zero-traffic claim is allowed. |
| D-008 | 2026-08-01 | Human ownership and compatibility policy are not auto-approved. | production plan prohibition on invented owners | Satisfied by explicit owner decision D-009. |
| D-009 | 2026-08-01 | Ian accepts every accountable owner role and approves the compatibility policy with a 90-day minimum overlap. | explicit user approval | Phase 0 exit gate passes; later production and retirement gates remain unchanged. |

## Risk register

| ID | Severity | Risk/evidence | Owner | Next action / target phase |
| --- | --- | --- | --- | --- |
| R-001 | critical | Only Railway production exists; no isolated local/CI PostGIS or release-candidate gate. | Ian | Build Phase 1 safe release path before contract/deployment changes. |
| R-002 | high | No checked-in CI workflow, dependency lock, or reproducible build definition. | Ian | Add disposable PostGIS CI, scanning, protocol smoke, and lock in Phase 1. |
| R-003 | high | Web startup runs migrations and `sync_public_intelligence`; one-time/source work is coupled to every boot. | Ian | Move to explicit release/predeploy jobs in Phase 1. |
| R-004 | high | One web replica and no Railway health-check path/timeout. | Ian | Add separate liveness/readiness and candidate traffic rejection in Phase 1. |
| R-005 | high | `Procfile` WSGI path cannot serve `/mcp/api/` but remains checked in. | Ian | Keep compatibility-only; add guard/documentation and remove only with evidence. |
| R-006 | high | Tool/source contract lacks ownership, sensitivity, limits, stability, schema versions, deadlines, and pagination metadata. | Ian | Extend authoritative registries in Phase 2. |
| R-007 | high | `gis_query_layer` accepts caller-selected `where`; safe complexity/operator/field semantics are not proven. | Ian | Constrain, version, privatize, or remove through reviewed Phase 4 decision. |
| R-008 | high | Enabled weekly GIS downloads were last checked 2026-07-13 and have no deployed schedule. | Ian | Schedule and alert in Phase 3. |
| R-009 | high | Land Ledger is Sedro-Woolley-only, rebuilt 2026-06-18, with no deployed rebuild schedule. | Ian | Make coverage explicit and schedule/verify before public tools. |
| R-010 | high | Tax statement fetches stop at 2026-06-26; 2,240 unresolved errors, zero slow-check rows, and no deployed job. | Ian | Define thresholds, repair run state, schedule checks in Phase 3. |
| R-011 | high | Latest assessor land step emitted 3,895 warnings without accepted/blocking classification. | Ian | Classify warning causes and trends in Phase 3. |
| R-012 | high | Zoning document `fetched_at` is null for all 313 documents; imports are not source-verification evidence. | Ian | Add verification dates/fingerprints and schedule in Phases 2-3. |
| R-013 | high | Cloudflare traffic, routes, deployed versions, crons, D1/R2, bindings, and secret names are unknown. | Ian | Restore authorized read access; do not retire assets. |
| R-014 | critical | Prior evidence found public unauthenticated ArcGIS/web/notify adapters with caller-selected targets. | Ian | Freeze; verify traffic/routes; prepare gated retirement. |
| R-015 | high | External legacy consumers remain unknown; source search is insufficient. | Ian | Export Cloudflare/Railway/OAuth evidence and interview owners in Phase 9. |
| R-016 | medium | `docs/platform-catalog.md` says 25 while runtime/public catalog says 31. | Ian | Generate docs/snapshot and fail CI on drift in Phase 2. |
| R-017 | medium | Unified smoke command covers seven in-process cases, not 31 authenticated protocol contracts. | Ian | Implement Phase 5 command specification. |
| R-018 | high | No demonstrated external MCP adoption; only three controlled calls on 2026-07-16. | Ian | Complete Phase 8 onboarding and Phase 9 beta before observation clock. |
| R-019 | high | Previous Nixpacks evidence reported runtime secrets promoted into build ARG/ENV metadata. | Ian | Reproduce safely in candidate, isolate build variables, then rotate as approved. |
| R-020 | high | Railway `postgres-volume` has no service ID and about 1 GB of data. | Ian | Identify contents, ownership, backups, and consumers; never delete on appearance. |
| R-021 | medium | Three expired smoke OAuth clients retain `active=true`; grants are inactive. | Ian | Define expiry/retention cleanup and test in Phase 7. |
| R-022 | medium | Census/soils are live-only with no durable status, fingerprints, or synthetic schedule. | Ian | Add source contracts/status and canaries in Phases 2-3/5. |
| R-023 | resolved | Ian accepted all human and credential-owner roles on 2026-08-01. | Ian | Closed in Phase 0. |
| R-024 | resolved | Ian approved the 90-day minimum breaking-change overlap on 2026-08-01. | Ian | Closed in Phase 0. |

## Phase transition rule

Phase 0 passed on 2026-08-01 after R-023 and R-024 were resolved. Phase 1
local-first work may begin while R-013, R-015, and later-retirement risks remain
blocked because it does not require Cloudflare mutation. Production deployment,
credential rotation, schedule creation, cost expansion, and any destructive
action require their later phase gates and explicit authority.
