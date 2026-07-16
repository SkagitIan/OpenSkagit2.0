# OpenSkagit Platform Catalog

Status: working consolidation inventory
Inventory date: 2026-07-16
Canonical project: `OpenSkagit-railway`
Canonical analytical store: Railway PostgreSQL/PostGIS

This catalog records the logical capabilities and physical deployments that make up OpenSkagit. A source configuration proves that a component is configured; it does not prove it is currently deployed. Cloudflare deployment state must be verified from an authenticated account before cutover or deletion.

## Catalog Rules

1. Every production capability has one canonical owner.
2. PostgreSQL/PostGIS is the system of record for parcel, assessor, GIS, zoning, tax, opportunity, graph, and audit data.
3. Public results preserve raw codes and readable descriptions together.
4. A deployment exists only for a documented operational reason: web serving, scheduled work, edge proxy/cache, notification delivery, or privileged isolation.
5. A deprecated component has a replacement, migration evidence, shutdown date, and deletion decision.
6. Secrets and credentials are never stored in this catalog.

## Canonical Capability Owners

| Capability | Canonical owner | Primary source | Notes |
| --- | --- | --- | --- |
| Assessor ingestion and change audit | `assessor_sync` | County export -> PostGIS | Nightly Railway job and sync audit records. |
| Live parcel verification | `assessor_mcp.services` | County Property OneStop | For freshness and fields absent from bulk imports. |
| Parcel search and presentation | Shared parcel services and `opportunity` | PostGIS first | Opportunity remains a feature app, not an MCP implementation. |
| GIS overlays | `gis_mcp.services` | PostGIS and ArcGIS REST | Layer definitions and bundles move to one registry. |
| Zoning interpretation | `zoning_mcp.services` | PostGIS and zoning corpus | Screening guidance with source citations, not legal determinations. |
| Opportunity screening | `opportunity` | PostGIS, zoning, graph | Preserve the distinction between signals and determinations. |
| Parcel/entity graph | `graph` | PostGIS-derived Kuzu artifacts | Preserve its internal identity boundary. |
| Tax analysis | `taxtool` | PostGIS tax tables/views | Tax year must be explicit where relevant. |
| Tax delinquency | `tax_delinquency` | County statements -> PostGIS | Freshness accompanies delinquency claims. |
| Analyst Q&A | `ask_agent` | Canonical services and read-only PostGIS | Same-process calls should not loop through a remote Worker. |
| Notifications | `opportunity` plus delivery adapter | PostGIS and email/webhooks | Separate delivery is justified for secret/failure isolation. |
| Source registry/health | Target shared `source_registry` | Versioned definitions + PostGIS status | Migrate useful verifier behavior from old `OpenSkagit`. |
| Unified tool interface | Target `openskagit_tools` | Delegates to canonical services | One authenticated MCP endpoint with modular domain code. |

## Implementation Status

- Phase 1 unified package: `openskagit_tools`
- Contract version: `1.0`
- Registered tools: 25 read-only parcel, GIS, Census/soils, and zoning tools
- Public catalog/access: `https://openskagit.com/mcp/`
- Canonical remote endpoint: `https://openskagit.com/mcp/api/`
- Transport: local stdio plus production Streamable HTTP in the Django ASGI deployment
- Authentication: approved OAuth clients, authorization code + PKCE, revocable grants, encrypted secrets, and `openskagit.read` scope
- Compatibility: separate assessor, GIS, and zoning MCP entries retained during cutover

## Current Tool Inventory

### Railway MCP servers

| Server | Tools | Target disposition |
| --- | --- | --- |
| `assessor-mcp` | Parcel details, history, sales, land, improvements, permits, tax detail, full report | Keep services; expose through unified façade; remove separate process later. |
| `gis-mcp` | Layers, metadata, parcel GIS, overlays, generic layer query | Keep services; expose through unified façade; remove separate process later. |
| `zoning-mcp` | Parcel resolution, profiles, use status, allowed uses, code search, standards, feasibility, comparisons | Keep services/citations; expose through unified façade; remove separate process later. |
| `django` | Commands, shell, checks, migrations | Keep local/admin-only; never expose through public MCP. |

### Cloudflare MCP tools

`OpenSkagit/worker` currently defines:

| Tool | Target owner |
| --- | --- |
| `search_parcels` | Shared parcel service |
| `get_property_context` | Unified façade composing narrower services |
| `get_property_summary` | Shared parcel service |
| `get_gis_overlays` | GIS service |
| `get_census_context` | GIS/context service |
| `get_soils_context` | GIS/context service |
| `list_gis_layers` | Shared source/layer registry |

The detailed Worker contract remains in `mcp-catalog.md`. During consolidation it is a compatibility contract, not the target architecture.

### Proposed unified groups

| Group | Proposed tools |
| --- | --- |
| Parcel | `parcel_search`, `parcel_get_summary`, `parcel_get_full_report`, `parcel_get_history`, `parcel_get_sales`, `parcel_get_land`, `parcel_get_improvements`, `parcel_get_permits`, `parcel_get_tax_detail` |
| GIS/context | `gis_list_layers`, `gis_get_layer_metadata`, `gis_get_parcel`, `gis_get_overlays`, `gis_query_layer`, `context_get_census`, `context_get_soils` |
| Zoning | `zoning_resolve_parcel`, `zoning_get_profile`, `zoning_lookup_use`, `zoning_list_allowed_uses`, `zoning_search_code`, `zoning_get_standards`, `zoning_get_overlays`, `zoning_build_feasibility`, `zoning_compare_zones` |
| Opportunity | `opportunity_search`, `opportunity_explain_match`, `opportunity_get_parcel_signals` |
| Reliability | `data_list_sources`, `data_get_source_status`, `data_get_freshness` |

Mutation tools such as saving searches, changing preferences, running syncs, or sending notifications require separate scopes and are excluded from the first read-only public catalog.

## Data Catalog

| Domain | Canonical relations | Rule |
| --- | --- | --- |
| Parcel | `skagit_parcels`, `assessor_rollup` | `parcel_number` is canonical; active parcels have `inactive_date IS NULL`. |
| Assessor detail | `sales`, `land`, `improvements`, `code_mappings` | Return raw codes and normalized descriptions together. |
| GIS | `gis_skagit_parcels` | Join `parcel_id` to `skagit_parcels.parcel_number`; geometry is SRID 4326. |
| Zoning | `parcel_primary_zoning`, `parcel_zoning`, `waza_zoning_zones` | Primary zoning is for one-zone display; full overlaps are for analysis. |
| Opportunity | `land_ledger_parcels`, `land_ledger_city_summary`, `v_land_ledger_source` | Labels are screening signals, not entitlement findings. |
| Tax | `v_parcel_tax_summary`, `v_parcel_tax_detail`, levy tables | Include the applicable tax year. |
| Delinquency | `tax_delinquency_taxstatement` | Include source freshness and payment timing. |
| Sync audit | `assessor_sync_runs`, `assessor_sync_files`, `assessor_sync_changes`, `assessor_sync_reports` | Provides provenance and change history. |

Cloudflare D1 `skagit-parcels` is a duplicate parcel store and is not a target system of record. Production usage must be measured before retirement.

The 2026-07-16 public baseline found 83,509 D1 parcel rows versus 83,391 active and 83,638 total PostGIS parcels. A golden D1 parcel had current assessor data embedded in a misplaced JSON field while its normalized analytical columns were null. D1 is neither count-identical nor shape-equivalent; preserve/export it for investigation, but do not use it as the canonical analytical source.

### Context source ownership

`context_mcp` is the canonical Census/soils implementation. Parcel geometry comes from PostGIS. Census geography matching uses the US Census geocoder; ACS data uses the official Census API when `CENSUS_API_KEY` is configured and otherwise the Census Reporter mirror pinned to ACS 2024 five-year estimates. Soils use NRCS Soil Data Access and the corrected `mapunit.farmlndcl` field. Ask Agent calls these services in-process rather than calling the legacy Worker.

Verification on 2026-07-16 used parcel P96023: all four ACS levels returned from release `acs2024_5yr` and NRCS returned one intersecting map unit. The legacy Worker returned missing-key errors for ACS and an invalid-field error for soils.

### Usage evidence

`McpToolCall` records secret-free tool name, caller class, outcome, duration, freshness marker, and exception class. It deliberately excludes arguments, parcel IDs, credentials, and result bodies. Review the adoption window with:

```powershell
python manage.py report_mcp_usage --days 30
```

Run the same-process source health suite with `python manage.py check_unified_mcp_catalog`. Compare the legacy D1 store without logging parcel payloads with `python manage.py audit_legacy_d1 --sample-size 25`.

## Deployment Catalog

### Railway

| Config | Workload | Schedule intent |
| --- | --- | --- |
| `railway.json` | Django web, public catalog, OAuth provider, unified MCP | Continuous |
| `railway.unified-mcp.json` | Static-bearer fallback MCP | Optional isolated fallback; not canonical |
| `railway.assessor-sync.json` | Assessor sync | Daily 10:00 UTC |
| `railway.build-parcel-graph.json` | Graph build/patterns | Daily 12:00 UTC |
| `railway.check-watched-parcels.json` | Watch checks | Daily 09:00 UTC |
| `railway.send-notifications.json` | Opportunity notifications | Daily 10:30 UTC |
| `railway.send-taxshift-notifications.json` | TaxShift notifications | Daily 10:45 UTC |
| `railway.taxshift-signups.json` | Signup processing | Every five minutes |
| `railway.tax-delinquency-backfill.json` | Historical backfill | One-off/worker; no cron in file |
| `railway.tax-delinquency-slow-check.json` | Slow refresh loop | Worker; no cron in file |

### Cloudflare configurations found in source

| Project | Worker | Function | Preliminary decision |
| --- | --- | --- | --- |
| `OpenSkagit/worker` | `skagit-agent-worker` | Property, GIS, Census, soils, HTTP MCP | Census/soils migrated; bridge remaining consumers; retire after zero-traffic evidence. |
| `workers/arcgis-adapter` | `arcgis-adapter` | ArcGIS proxy | Merge; retire unless edge value is proven. |
| `workers/web-adapter` | `web-adapter` | Web proxy | Keep only if Cloudflare egress is necessary. |
| `workers/notify-adapter` | `notify-adapter` | Email/webhook delivery | Keep provisionally for isolation. |
| `skagit-pipeline` | `skagit-parcels` | D1/R2 API, NL-to-SQL, geo cron | Freeze and retire after parity/traffic checks. |
| `cloudflared` | `skagit-parcels` | Older D1 endpoint | Highest-priority deletion candidate after deployment check. |

## Source Registry Consolidation

Three registries overlap:

1. `gis_mcp/layers.py`: richest GIS layer/bundle definitions.
2. `OpenSkagit/catalog/seeds/*.yaml`: older runtime source catalog.
3. `OpenSkagit/registry/sources/*.yaml`: duplicated documentation definitions.

Target: one versioned definition format with stable ID, owner, domain, endpoint, layer ID, spatial reference, refresh policy, verification probe, authentication class, and status. Runtime database records are derived from it.

## Common Result Contract

```json
{
  "data": {},
  "sources": [{"source_id": "...", "url": "...", "retrieved_at": "..."}],
  "freshness": {"as_of": "...", "status": "fresh|stale|unknown"},
  "warnings": [],
  "errors": []
}
```

Coded fields include raw and readable values, such as `zone_id` plus `zone_name`, or `condition_cd` plus `condition_description`.

## Maintenance

- Update this file when a production capability moves or changes.
- Update `mcp-catalog.md` when a public tool contract changes.
- Update `deprecation-register.md` when a replacement advances.
- Review deployments quarterly and after infrastructure migrations.
- Never mark a component deleted until traffic, data, rollback, route, schedule, binding, and secret checks pass.
