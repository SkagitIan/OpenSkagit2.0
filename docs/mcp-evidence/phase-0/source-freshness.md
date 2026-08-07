# Phase 0 Source Freshness Baseline

Inspection date: 2026-08-01  
Method: read-only aggregate ORM/SQL queries against the configured PostGIS
connection. No parcel, owner, graph identity, request argument, raw source
payload, source URL credential, or filesystem path was exported.

This is evidence of stored timestamps and coverage, not a final Phase 3 freshness
policy. Until source contracts define `effective_at`, `verified_at`, thresholds,
and composite-state rules, this report does not relabel retrieval time as the
effective date.

## Assessor bulk sync

Latest run: 46  
Started: 2026-08-01T10:01:50Z  
Finished: 2026-08-01T10:04:18Z  
Status: success

| Dataset | Staged | Inserted | Updated | Applied | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: |
| assessor rollup | 83,650 | 4 | 395 | 399 | 0 |
| sales | 352,399 | 31 | 131 | 193 | 0 |
| land | 106,623 | 0 | 4 | 4 | 3,895 |
| improvements | 308,639 | 0 | 120 | 120 | 1 |

The attached auditor step succeeded for its 2026-07-30 through 2026-08-01
window: 59 document types, 40 results parsed, 40 inserted, zero query errors,
and zero page caps.

Finding: the run is current and successful, but the 3,895 land warnings are not
yet classified as expected/accepted or release-blocking. Phase 3 owns that
classification and alert threshold.

## Canonical PostGIS coverage

| Aggregate | Value |
| --- | ---: |
| Active assessor parcels | 83,391 |
| Total assessor parcels | 83,638 |
| Maximum parcel tax year | 2026 |
| GIS parcel polygons | 82,449 |
| Primary zoning rows | 72,040 |
| Full parcel-zone overlaps | 126,329 |

These values match the existing schema reference snapshot for the total and
spatial relations. Coverage percentages and invariant thresholds are intentionally
deferred to Phase 3 rather than inferred here.

## Downloadable GIS source files

The source configuration declares weekly refresh for 15 entries. Twelve are
enabled and three are disabled. Every enabled row reports `unchanged` with its
last successful download between 2026-07-13T17:00:37Z and
2026-07-13T17:00:48Z. That is about 19 days before this inspection and exceeds
the declared weekly cadence.

| Layer | Enabled | Last status | Last download UTC |
| --- | --- | --- | --- |
| address ranges | yes | unchanged | 2026-07-13T17:00:48Z |
| city limits | yes | unchanged | 2026-07-13T17:00:40Z |
| comprehensive plan | yes | unchanged | 2026-07-13T17:00:43Z |
| fire districts | yes | unchanged | 2026-07-13T17:00:44Z |
| historical sites | yes | unchanged | 2026-07-13T17:00:43Z |
| parcel numbers | yes | unchanged | 2026-07-13T17:00:40Z |
| parcels | yes | unchanged | 2026-07-13T17:00:37Z |
| public places | yes | unchanged | 2026-07-13T17:00:44Z |
| roads | yes | unchanged | 2026-07-13T17:00:47Z |
| school districts | yes | unchanged | 2026-07-13T17:00:44Z |
| tide gates | yes | unchanged | 2026-07-13T17:00:43Z |
| voting precincts | yes | unchanged | 2026-07-13T17:00:45Z |
| flood zones | no | disabled | never |
| shoreline | no | disabled | never |
| zoning package | no | disabled | never |

No deployed Railway service runs `sync_gis_sources`; the checked-in command is
operator-only today.

## Zoning corpus

| Aggregate | Value |
| --- | ---: |
| Jurisdictions | 7 |
| Zones | 103 |
| Structured use rules | 5,260 |
| Source documents | 313 |
| Imported sections | 3,191 |
| Imported source tables | 146 |
| Latest section import | 2026-06-30T02:21:06Z |
| Latest source-table import | 2026-06-30T02:21:06Z |

All 313 `ZoningCodeDocument.fetched_at` values are null. Import timestamps prove
when normalized records were written, but do not prove when the official source
text was fetched or last verified. No deployed Railway verification/import job
was found.

## Reviewed public budgets

| Aggregate | Value |
| --- | ---: |
| Jurisdictions | 9 |
| Documents | 9 |
| Published documents | 7 |
| Current documents | 7 |
| Reviewed line items | 111 |
| Maximum fiscal year | 2026 |
| Latest retrieval | 2026-07-22T13:52:08Z |
| Latest review | 2026-07-22T14:28:09Z |

The latest import run succeeded on 2026-07-22 and extracted 48 pages. No deployed
Railway budget coverage or freshness verification job was found. Two of nine
documents are not published/current; Phase 3 must define coverage expectations
per jurisdiction rather than treating document count as completeness.

## Land Ledger

One jurisdiction is materialized:

| City | Parcels | Zoned | Unknown zone | Rebuilt | Assumption version |
| --- | ---: | ---: | ---: | --- | --- |
| Sedro-Woolley | 3,971 | 3,969 | 2 | 2026-06-18T20:17:06Z | `scenario-value-v1` |

No deployed Railway Land Ledger rebuild service was found. The current one-city
coverage must remain explicit and must not be described as countywide.

## Tax delinquency

| Aggregate | Value |
| --- | ---: |
| Materialized parcel/year statements | 58,306 |
| Earliest source fetch | 2026-06-23T16:46:01Z |
| Latest source fetch | 2026-06-26T09:43:26Z |
| Maximum tax year | 2026 |
| Lightweight check rows | 0 |
| Unresolved error records | 2,240 |

The latest completed backfill ran 2026-06-25 through 2026-06-26 for tax years
2023-2026: 72,386 parcels considered, 106,980 statements attempted, 106,223
saves, 182,564 skips, and 757 errors. Its run status is `success`, but the error
rate and current 2,240 unresolved error rows require Phase 3 policy.

An older backfill row from 2026-06-24 still has status `running` with no finish
time. Treat this as stale run-state evidence to investigate, not as proof that a
process is still active. No deployed Railway backfill or slow-check service was
found, and `TaxStatementCheck` contains no rows.

## Live-only Census and soils

- Census uses a configured ACS year with code default `2024`, Census geocoding,
  and either the official ACS API or Census Reporter fallback.
- Soils uses live NRCS Soil Data Access SSURGO queries intersected with the
  PostGIS parcel geometry.
- Neither source has durable source-status storage, last-success tracking,
  schema fingerprints, or scheduled verification today.
- The Phase 0 repository tests cover response shaping and failure envelopes, but
  Phase 0 did not create a production upstream call.

## Schedule gaps to carry into Phase 3

| Source family | Expected/needed operation | Deployed schedule |
| --- | --- | --- |
| Assessor bulk/auditor | daily sync | yes |
| GIS downloads | weekly verification/download | no |
| Zoning corpus | verification and controlled re-import | no |
| Budgets | coverage/source verification | no |
| Land Ledger | rebuild at approved cadence | no |
| Tax delinquency | slow check and stale-row refresh | no |
| Census/soils | synthetic verification/live-only policy | no |

No schedule was added in Phase 0.
