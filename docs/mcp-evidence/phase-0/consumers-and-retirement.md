# Phase 0 Consumers, Credentials, Storage, and Retirement Candidates

Inspection date: 2026-08-01

This inventory classifies evidence; it does not authorize shutdown, deletion,
credential revocation, route changes, or storage mutation.

## Canonical consumer/adoption evidence

The supported operator command was run as:

```text
railway run .\.venv\Scripts\python manage.py report_mcp_usage --days 30
```

It returned three successful controlled OAuth smoke calls and no failures:

| Tool | Caller class | Calls | Failures | Average/max ms | Last call UTC |
| --- | --- | ---: | ---: | --- | --- |
| `context_get_census` | `mcp-http-oauth` | 1 | 0 | 755 / 755 | 2026-07-16T12:28:31Z |
| `context_get_soils` | `mcp-http-oauth` | 1 | 0 | 468 / 468 | 2026-07-16T12:28:29Z |
| `parcel_search` | `mcp-http-oauth` | 1 | 0 | 14 / 14 | 2026-07-16T12:52:56Z |

Sanitized OAuth aggregates:

- access requests: zero;
- OAuth client rows: three, all labeled as production/final smoke clients;
- all three client rows have `active=true` but expired on 2026-07-17;
- grants: three total, zero active;
- last OAuth client/grant use: 2026-07-16T01:03:45Z; and
- tool telemetry rows: three total.

Conclusion: the canonical endpoint has controlled validation evidence but no
external adoption evidence. The expired-but-active client records also demonstrate
a future retention/cleanup requirement; no record was altered in Phase 0.

## Known consumer classes

| Consumer class | Current evidence | Status/action |
| --- | --- | --- |
| Public ChatGPT/Claude clients | no access requests, sessions, or calls | not adopted; Phase 8-9 onboarding required |
| Controlled OAuth smoke clients | three expired client rows, inactive grants, three calls | test evidence only; retain until cleanup policy is approved |
| Canonical web catalog | public `/mcp/` links to `/mcp/api/` | canonical `KEEP` |
| Local unified stdio | `.mcp.json` entry `openskagit` | supported local developer path |
| Local assessor/GIS/zoning stdio | three compatibility entries in `.mcp.json` | `BRIDGE`; migrate local users before removal |
| Local Django MCP admin server | `.mcp.json` entry `django` and `mcp_django.py` | local/admin only; never public |
| Railway application code | source search shows same-process services and only intentional read-only D1 audit URL | no legacy Worker dependency found |
| External legacy Worker callers | source search cannot identify them | unknown until authenticated Cloudflare traffic export |
| Older `OpenSkagit/agent` | source remains and documents adapter use | source/reference candidate; not in Railway production service list |
| Top-level `Factory/mcp` | separate Django source tree | archive candidate; deployment/consumers not demonstrated |

Source-code search is not treated as proof of zero external consumers.

## Railway component classification

| Component | Classification | Replacement/role | Retirement status |
| --- | --- | --- | --- |
| `web` / `OpenSkagit-railway` | deployed `KEEP` | canonical site, OAuth, and MCP | not a candidate |
| Railway `PostGIS` | deployed `KEEP` | canonical analytical store | not a candidate |
| `assessory sync` | deployed `KEEP` | current assessor/auditor freshness | harden schedule/alerts |
| `taxshift-signups` | deployed non-MCP product job | TaxShift workflow | outside MCP retirement without product-owner approval |
| `send-taxshift-notifications` | deployed non-MCP product job | TaxShift workflow | outside MCP retirement without product-owner approval |
| standalone unified MCP manifest | not deployed fallback | canonical web endpoint is replacement | retain as fallback until owner decision |
| source-only graph/watch/opportunity/tax manifests | not deployed | potential future jobs | classify schedule need in Phase 3; do not assume retired |
| `Procfile` WSGI web | not authoritative | `railway.json` ASGI | compatibility-only source |

## Cloudflare source-configured inventory

Local source still identifies:

| Source path | Configured Worker/resource | Source-known role | Classification |
| --- | --- | --- | --- |
| `OpenSkagit/worker` | `skagit-agent-worker` | legacy HTTP MCP/property/GIS/context | `BRIDGE` then retirement after gates |
| `OpenSkagit/workers/arcgis-adapter` | `arcgis-adapter` | public ArcGIS proxy | frozen urgent retirement candidate |
| `OpenSkagit/workers/web-adapter` | `web-adapter` | public web proxy | frozen urgent retirement candidate |
| `OpenSkagit/workers/notify-adapter` | `notify-adapter` | notification delivery boundary | frozen urgent retirement candidate |
| `OpenSkagit/skagit-pipeline` | `skagit-parcels`, D1 and R2 bindings | duplicate parcel pipeline/API | `FREEZE`; export/observe before retirement |
| `OpenSkagit/cloudflared` | duplicate `skagit-parcels` config | older duplicate endpoint | `VERIFY`; identity unknown |

The separate `SkagitIan/skagit-pipeline` repository remains at revision `0e598da`.
Its latest five weekly ingest runs, through 2026-07-12, all failed. The last run
was a scheduled failure. That is writer-risk evidence, not proof that Cloudflare
cron, reads, or every deployed version is inactive.

`npx wrangler whoami` returned `Not logged in` after an HTTP 400 token failure.
The following remain explicitly blocked:

- account and zone identity;
- deployed Worker versions/source revisions;
- routes and custom domains;
- traffic analytics by Worker/route;
- cron triggers and execution history;
- D1 databases, live counts, writers, and backups;
- R2 buckets, object counts, retention, and consumers;
- bindings and secret **names**; and
- Cloudflare credential owner.

The canonical `openskagit.com` DNS/proxy is a protected `KEEP` boundary distinct
from standalone Worker retirement.

## Storage inventory

| Store | Evidence | Disposition |
| --- | --- | --- |
| Railway `postgis-volume` | attached to PostGIS; about 2,099 MB / 5,000 MB | `KEEP`; backup/restore evidence required |
| Railway `postgres-volume` | no service ID; about 1,014 MB / 5,000 MB | `VERIFY`; possible orphan, never delete without contents/backup/owner evidence |
| Cloudflare D1 `skagit-parcels` | source binding known; live account inventory blocked | `FREEZE`; export, parity, traffic, backup, and approval gates |
| Cloudflare R2 `raw-parcels` | source binding known; account inventory blocked | `VERIFY`; inventory and retention decision required |
| Budget document object storage | application configuration exists; no Phase 0 account inventory | `KEEP`; include in Phase 7 backup/RPO work |
| Local GIS downloads/extractions | paths tracked in database but not exported here | operational cache/source copies; retention policy TBD |

## Credential-class inventory

No values are recorded.

| Credential class | Known use | Human owner | Phase 0 access/evidence |
| --- | --- | --- | --- |
| Railway project/deploy access | production topology and operator commands | Ian | CLI read access works |
| PostGIS connection | canonical application/database | Ian | configured read queries work |
| MCP OAuth client secrets | approved public clients | Ian | encrypted at rest; three expired smoke clients observed |
| Django secret/encryption material | app signing and current OAuth-secret encryption derivation | Ian | existence inferred from working app; value not read |
| Cloudflare/Wrangler | Workers, D1, R2, traffic, bindings | Ian | blocked/not logged in |
| R2/S3-compatible budget storage | budget PDFs | Ian | not inventoried at account level |
| Resend/notification credentials | application notification jobs | Ian | no value or variable inspected |
| Census API key | optional official ACS access | Ian | presence/value not inspected |
| Sentry/telemetry credentials | error monitoring | Ian | presence/value not inspected |

## Retirement matrix

| Candidate | Replacement identified | Consumer evidence | Unique data/backup | Traffic evidence | Phase 0 result |
| --- | --- | --- | --- | --- | --- |
| Separate assessor/GIS/zoning MCP processes | unified registry delegates to same services | local `.mcp.json` entries remain | no unique store identified | external use unknown | `BRIDGE`; not safe to remove |
| `skagit-agent-worker` | canonical parcel/GIS/context tools | Railway cut over; external unknown | source only or legacy state needs verification | blocked | not safe to remove |
| ArcGIS/web/notify adapters | direct canonical services/jobs | Railway has no source reference; external unknown | no unique store expected, secrets/routes unknown | blocked | frozen; urgent review, no shutdown |
| D1/R2 parcel pipeline | PostGIS and assessor sync | Railway cut over; external unknown | unique/malformed legacy state and R2 objects require export | blocked | not safe to remove |
| top-level `Factory/mcp` | `assessor_mcp.services` and unified MCP | local/external unknown | fixtures/parser parity required | not applicable/unknown | archive candidate only |
| `OpenSkagit/agent`, catalog, registry | canonical Django services and future source registry | not deployed in Railway; source consumers unknown | case-file/catalog retention undecided | not applicable/unknown | merge/archive candidate only |
| Railway `postgres-volume` | likely current PostGIS volume, but identity unproven | none identified | contents and backup unknown | not applicable | automatic stop; investigate only |

Every destructive retirement gate remains closed.
