# Phase 0 Repository and Deployment Baseline

Inspection date: 2026-08-01

## Repository identity

| Field | Observed value |
| --- | --- |
| Canonical repository | `OpenSkagit-railway` |
| Git branch | `railway-django-scratch` |
| Git revision | `b2a4de6bc96bdffa68306bea91163dc1973e881f` |
| Revision date | 2026-07-31T11:26:56-07:00 |
| Revision subject | `Update public read and deployment documentation` |
| Pre-existing working-tree state | `docs/PROD_MCP_PLAN.md` untracked |
| Python policy | 3.12 in repository instructions |
| Framework | Django 5.2, PostgreSQL/PostGIS only |
| Public MCP transport | Django ASGI plus FastMCP Streamable HTTP |

The production plan file is user-owned baseline input. It was not overwritten or
normalized during Phase 0.

## Runtime contract path

- `openskagit_tools/registry.py` defines 31 `ToolContract` entries.
- `openskagit_tools/handlers.py` defines the matching thin domain delegates.
- `openskagit_tools/mcp_server.py` refuses to build if registry and handlers differ.
- `openskagit_tools/views.py` renders the public count from the same registry.
- `config/asgi.py` mounts the OAuth-enabled Streamable HTTP application at
  `/mcp/api/` and the OAuth metadata/protocol routes.
- Local tests prove the registry, handler set, FastMCP `tools/list`, and public
  catalog use the same current registry.

Current contract fields are limited to name, domain, description, source IDs,
read-only status, and contract version. Phase 2 must add ownership, stability,
input/output versions, sensitivity, limits, deadlines, pagination, cache policy,
and public-use limitations.

## Management-command inventory

Fifty non-`__init__` commands are checked in:

| App | Commands |
| --- | --- |
| `ask_agent` | `check_mcp_catalog`, `check_unified_mcp_catalog`, `eval_ask` |
| `assessor_sync` | `build_geo_features`, `check_watched_parcels`, `export_geo_features_parquet`, `import_assessor`, `sync_assessor_data`, `sync_gis_sources` |
| `budgets` | `check_budget_r2`, `eval_budgets`, `import_budget_catalog`, `import_budget_lines`, `import_budget_pdf`, `load_jurisdiction_population`, `load_reviewed_budgets`, `publish_budget_document` |
| `core` | `build_sedro_parcels`, `create_superuser_ian` |
| `discovery_agent` | `discover_current_test`, `run_current_probes` |
| `gis_mcp` | `check_gis_mcp` |
| `graph` | `build_graph_entities`, `build_parcel_adjacency`, `build_parcel_graph`, `run_graph_patterns` |
| `land_ledger` | `ensure_land_ledger`, `rebuild_land_ledger` |
| `openskagit_tools` | `approve_mcp_access`, `audit_legacy_d1`, `report_mcp_usage` |
| `opportunity` | `run_opportunity_ai_evals`, `send_notifications`, `sync_public_intelligence` |
| `parcelbook` | `build_parcel_search` |
| `regression` | `build_sfr_sales_model_dataset`, `run_neighborhood_compliance_loop`, `run_sfr_baseline_ratio_study` |
| `tax_delinquency` | `backfill_tax_statements`, `slow_check_tax_statements` |
| `taxtool` | `evaluate_taxshift_report_data`, `fetch_parcel_history`, `fetch_tax_statement_poc`, `load_levy_history`, `process_taxshift_signups`, `send_taxshift_notifications` |
| `zoning_mcp` | `check_zoning_mcp`, `check_zoning_regressions`, `import_zoning_corpus`, `load_zoning_seed` |

The explicit correction in the final row prevents a GIS/zoning ownership mix-up in
operator documentation.

### Unified smoke-command finding

`check_unified_mcp_catalog` is present and tracked since commit `811301d` on
2026-07-16. It aliases `check_mcp_catalog`, which:

- calls handlers in-process rather than the Streamable HTTP protocol;
- checks seven representative tools rather than all 31;
- has no OAuth client flow;
- has no local/release-candidate/production target selection; and
- has per-source environment timeouts but no hard whole-case cancellation.

Therefore the production plan's statement that the command is absent is stale.
The correct baseline is **present but below the Phase 5 specification**.

## Test inventory and result

- 36 checked-in Python test files were enumerated.
- `python manage.py test openskagit_tools --verbosity 2` found 24 tests.
- All 24 passed on 2026-08-01 in 1.429 seconds of test execution.
- Django system checks reported no issues.
- The suite used `SimpleTestCase` and skipped database creation; it is not a
  disposable PostGIS integration test.

## Build, CI, and dependency state

| Area | Observed state |
| --- | --- |
| Dependency declaration | unpinned `requirements.txt` ranges and bare packages |
| Lock file | none |
| Dockerfile | none |
| Local/CI PostGIS compose definition | none |
| Checked-in GitHub Actions workflow | none in canonical repository |
| GitHub repository workflow | GitHub-managed `Dependency Graph` only; not CI |
| Release-candidate environment | none |
| Environments | Railway `production` only |

## Deployment-manifest decision

| File | Classification | Evidence and rule |
| --- | --- | --- |
| `railway.json` | **Canonical** | Deployed by `web`; starts Django ASGI/Uvicorn and serves `/mcp/api/`. Phase 1 must separate migrations, `sync_public_intelligence`, and other release work from web startup. |
| `Procfile` | **Compatibility-only** | Its `web` entry uses Gunicorn WSGI, runs migrations/sync/Land Ledger/static work at boot, and cannot serve the ASGI MCP route. It is not an authoritative production path. |
| `railway.unified-mcp.json` | **Fallback, not deployed** | Static-bearer standalone FastMCP service; retained only as an isolated fallback and not the canonical OAuth endpoint. |
| Other `railway.*.json` | **Job/service manifests** | Each is classified below as deployed or source-only. |

This decision implements the user's 2026-08-01 instruction that the production
plan supersedes the former startup rule.

## Checked-in Railway manifest inventory

| Manifest | Intended command | Schedule in source | Production state |
| --- | --- | --- | --- |
| `railway.json` | migrate, public-intelligence sync, static collection, ASGI/Uvicorn | none | deployed as `web` |
| `railway.assessor-sync.json` | `sync_assessor_data` | `0 10 * * *` | deployed as `assessory sync` |
| `railway.taxshift-signups.json` | `process_taxshift_signups --once` | every five minutes | deployed as `taxshift-signups` |
| `railway.send-taxshift-notifications.json` | `send_taxshift_notifications` | `45 10 * * *` | deployed |
| `railway.build-parcel-graph.json` | graph entity/adjacency/build/pattern pipeline | `0 12 * * *` | source-only; no production service |
| `railway.check-watched-parcels.json` | `check_watched_parcels` | `0 9 * * *` | source-only; no production service |
| `railway.send-notifications.json` | opportunity daily notifications | `30 10 * * *` | source-only; no production service |
| `railway.tax-delinquency-backfill.json` | tax statement backfill | none | source-only; no production service |
| `railway.tax-delinquency-slow-check.json` | continuous/aged slow check | none | source-only; no production service |
| `railway.unified-mcp.json` | standalone static-bearer MCP | none | source-only fallback |

## Railway production topology

Read-only `railway status --json` reported one accessible environment named
`production`, five services, and two volume records.

| Service | Deployment | State | Replica/health evidence | Domains or storage |
| --- | --- | --- | --- | --- |
| `web` | `9b97b928-0455-4411-9e87-a549f34d09b6` | success, running, revision `b2a4de6` | one replica; health path and timeout null | Railway domain plus `openskagit.com` and `taxshift.co` |
| `PostGIS` | `2283250e-0cd7-425d-8499-e53301aa5c7a` | success, running | one replica; platform health path null | `postgis-volume`, about 2,099 MB used of 5,000 MB |
| `assessory sync` | `5a2dad14-6339-438b-b49a-3e46b53f8cda` | success, stopped between cron runs | one job replica; no health path | daily manifest |
| `taxshift-signups` | `6d0e4f56-a333-4b40-8129-2730a8cec183` | success, stopped between cron runs | one job replica; no health path | five-minute manifest |
| `send-taxshift-notifications` | `722089d6-f5ec-4326-b827-78d5df25f98a` | success, stopped between cron runs | one job replica; no health path | daily manifest |

A second volume record named `postgres-volume` has no service ID, is mounted at
`/var/lib/postgresql/data`, and reports about 1,014 MB used of 5,000 MB. Treat it
as an orphan candidate requiring owner and backup investigation, never as an
authorized deletion target.

## Public production boundary

Probes on 2026-08-01 returned:

- `GET https://openskagit.com/mcp/`: 200 HTML and `31 read-only tools`.
- `GET /.well-known/oauth-authorization-server`: 200 JSON; issuer and endpoints
  use HTTPS; authorization-code and refresh-token grants, revocation,
  client-secret authentication, S256 PKCE, and `openskagit.read` are advertised.
- `GET /.well-known/oauth-protected-resource/mcp/api/`: 200 JSON; canonical
  resource is `https://openskagit.com/mcp/api/` and bearer-header auth is advertised.
- Unauthenticated MCP `initialize` POST: 401 JSON.

No authenticated production tool call was created during Phase 0.
