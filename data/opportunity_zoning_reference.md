# Opportunity Zoning Reference

This document summarizes zoning and comp-plan values visible to the DuckDB/R2
Opportunity AI Search engine. At runtime, `opportunity.r2_search` appends a live
summary from the `zoning_mcp` database: jurisdictions, zones, structured use
rules, imported code sections, and source tables. This file is the stable prompt
guidance; `zoning_mcp` is the source-code/legal context. Both are grounding
context, not final permit or entitlement determinations.

Primary R2 fields:

- `derived/parcel_search.parquet.zoning_code_short`
- `derived/parcel_search.parquet.zoning_label`
- `derived/parcel_search.parquet.zoning_code`
- `derived/parcel_search.parquet.comp_plan_lud`
- `derived/parcel_search.parquet.city_name`
- `derived/parcel_search.parquet.inside_city_limits`
- `geoparquet/compplan.parquet.ZONING_COD`
- `geoparquet/compplan.parquet.ZONING_LAB`
- `geoparquet/compplan.parquet.LUD`
- `geoparquet/compplan.parquet.LUD_ZONING`

Primary zoning_mcp sources:

- `zoning_mcp.Jurisdiction`: jurisdiction metadata, source URLs, extraction status.
- `zoning_mcp.Zone`: source-code zone codes and names by jurisdiction.
- `zoning_mcp.ZoningUseRule`: structured permitted/conditional/prohibited use rows.
- `zoning_mcp.ZoningCodeSection`: imported code section text and references.
- `zoning_mcp.ZoningSourceTable`: imported source tables, including use and dimensional standards tables.

## Core Rules

1. Zoning fields are screening context, not permit/entitlement determinations.
2. Do not infer residential zoning with `zoning_code_short LIKE 'R%'` only.
   Skagit County zoning codes include residential-ish values such as `RI`, `RRv`,
   `RVR`, `URR`, and `BR-R`, while incorporated city parcels often appear as
   `CITY` / `Incorporated Area`.
   Source zoning codes from `zoning_mcp` may use different normalized forms, such
   as Sedro-Woolley `R_1`, `R_5`, `R_7`, and `R_15`.
3. For prompts asking for residential zones only, combine requested asset evidence
   with zoning evidence. A strict SFR prompt still needs SFR land-use or dwelling
   evidence; zoning alone is not enough.
4. For named city searches, `CITY` means incorporated area but not which city by
   itself. Pair it with `city_name` or `situs_city_state_zip`.
5. County/UGA zoning labels can mix broad planning areas with parcel use. Treat UGA,
   urban reserve, and city labels as context unless the prompt explicitly asks for
   zoning/UGA.

## Residential-Oriented Zoning Signals

Use these as positive zoning/context signals for residential-zone prompts when the
parcel asset class also matches the prompt.

| Code | Label / Meaning | Notes |
| --- | --- | --- |
| `RI` | Rural Intermediate | Strong county residential/rural residential signal. |
| `RRv` | Rural Reserve | Often residential/rural residential in parcel data. |
| `RVR` | Rural Village Residential | Residential village signal. |
| `URR` | Urban Reserve Residential | UGA/urban reserve residential signal. |
| `BR-R` | Bayview Ridge Residential | Residential UGA signal. |
| `R` | Swinomish Residential | Tribal/UGA residential label. |
| `RRc-NRL` | Rural Resource - NRL | Mixed rural/resource; can contain SFR but should be a weaker residential signal. |
| `CITY` | Incorporated Area | Use with `city_name` and SFR/residential land-use evidence; not inherently a residential zone by itself. |

Example residential-zone predicate for parcel screening:

```sql
AND (
  ps.zoning_code_short IN ('RI', 'RRv', 'RVR', 'URR', 'BR-R', 'R')
  OR lower(COALESCE(ps.zoning_label, '')) LIKE '%residential%'
  OR (
    ps.zoning_code_short = 'CITY'
    AND lower(COALESCE(ps.city_name, '')) = 'sedro-woolley'
    AND land_use_code IN (111, 112, 113)
  )
)
```

For "Sedro-Woolley or immediate vicinity" residential searches, use both:

```sql
lower(COALESCE(ps.city_name, '')) = 'sedro-woolley'
OR lower(COALESCE(ps.situs_city_state_zip, '')) LIKE '%sedro%'
```

The postal/vicinity branch is important because many Sedro-Woolley-area SFR parcels
have `city_name IS NULL` and `situs_city_state_zip = 'SEDRO WOOLLEY, WA 98284'`.

## Resource / Natural Resource Signals

Treat these as resource, agricultural, forestry, or natural-resource context. They
may contain existing residences, but they are not residential-zone matches unless
the prompt allows rural/resource residential context.

| Code | Label / Meaning |
| --- | --- |
| `Ag-NRL` | Agricultural - NRL |
| `IF-NRL` | Industrial Forest - NRL |
| `SF-NRL` | Secondary Forest - NRL |
| `RRc-NRL` | Rural Resource - NRL |
| `OSRSI` | Public Open Space of Regional/Statewide Importance |

## Commercial / Industrial / Business Signals

Use these as positive context for commercial, industrial, business, service, or
redevelopment prompts when land-use evidence also supports the asset class.

| Code | Label / Meaning |
| --- | --- |
| `RB` | Rural Business |
| `RVC` | Rural Village Commercial |
| `RC` | Rural Center |
| `SSB` | Small-Scale Business |
| `URC-I` | Urban Reserve Commercial Industrial |
| `BR-LI` | Bayview Ridge Light Industrial |
| `BR-HI` | Bayview Ridge Heavy Industrial |
| `NRI` | Natural Resource Industrial |
| `RMI` | Rural Marine Industrial |
| `RFS` | Rural Freeway Service |
| `AVR` | Aviation Related |
| `AVR-L` | Aviation Related - Limited |
| `C` | Swinomish Commercial |

## Open Space / Recreation / Public Signals

Use these as positive evidence for public/open-space/recreation prompts and as
exclusion/risk context for private investment or private bare-lot prompts.

| Code | Label / Meaning |
| --- | --- |
| `OSRSI` | Public Open Space of Regional/Statewide Importance |
| `URP-OS` | Urban Reserve Public Open Space |
| `SRT` | Small-Scale Recreation & Tourism |
| `MPR` | Master Planned Resort |

## UGA / Urban Development District Signals

These values indicate urban growth area or development-district context. They are
not enough by themselves to prove a parcel is residential, commercial, or industrial.
Pair them with land-use, zoning label, city/place, and improvement evidence.

| Code | Label / Meaning |
| --- | --- |
| `A-UD` | Anacortes UGA Development District |
| `B-UD` | Burlington UGA Urban Development District |
| `LC-UD` | La Conner UGA Urban Development District |
| `MV-UD` | Mount Vernon UGA Urban Development District |
| `H-URv` | Hamilton Urban Reserve |
| `UGA` | Urban Growth Area |

## Common Parcel-Search Zoning Values

These are high-frequency combinations observed in
`derived/parcel_search.parquet`. Counts are approximate grounding context and may
change when R2 data is rebuilt.

| zoning_code_short | zoning_label | comp_plan_lud | parcel_count | residential_use_count | commercial_use_count | resource_land_count |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `CITY` | Incorporated Area | `CITY` | 33724 | 25454 | 2721 | 2735 |
| `RRv` | [RRv] Rural Reserve | `RRV` | 11949 | 7854 | 56 | 3743 |
| `Ag-NRL` | [Ag-NRL] Agricultural - NRL | `A` | 6903 | 2146 | 46 | 4490 |
| `RI` | [RI] Rural Intermediate | `RI` | 6023 | 4546 | 21 | 1309 |
| `RVR` | [RVR] Rural Village Residential | `RV` | 3095 | 2305 | 59 | 658 |
| `IF-NRL` | [IF-NRL] Industrial Forest - NRL | `IF` | 3087 | 964 | 15 | 1952 |
| `OSRSI` | [OSRSI] Public Open Space of Regional/Statewide Importance | `OSRSI` | 1596 | 151 | 25 | 1166 |
| `R` | Swinomish Residential | `SWINOMISH UGA` | 1491 | 286 | 3 | 1194 |
| `RRc-NRL` | [RRc-NRL] Rural Resource - NRL | `RR` | 1470 | 432 | 15 | 867 |
| `SF-NRL` | [SF-NRL] Secondary Forest - NRL | `SF` | 1179 | 369 | 4 | 740 |
| `URR` | [URR] Urban Reserve Residential | multiple UGAs | 2287 | 2015 | 9 | 237 |
| `BR-R` | [BR-R] Bayview Ridge Residential | `BAY VIEW RIDGE UGA` | 785 | 746 | 0 | 28 |
| `BR-LI` | [BR-LI] Bayview Ridge Light Industrial | `BAY VIEW RIDGE UGA` | 166 | 7 | 61 | 66 |
| `A-UD` | [A-UD] Anacortes UGA Development District | `ANACORTES UGA` | 165 | 16 | 12 | 44 |
| `RB` | [RB] Rural Business | `RB` | 96 | 23 | 49 | 15 |
| `BR-HI` | [BR-HI] Bayview Ridge Heavy Industrial | `BAY VIEW RIDGE UGA` | 71 | 0 | 8 | 25 |
| `URC-I` | [URC-I] Urban Reserve Commercial Industrial | multiple UGAs | 114 | 24 | 56 | 16 |
| `RVC` | [RVC] Rural Village Commercial | `RVC` | 54 | 11 | 36 | 4 |
| `NRI` | [NRI] Natural Resource Industrial | `NRI` | 30 | 4 | 6 | 7 |
| `MPR` | [MPR] Master Planned Resort | `MPR` | 21 | 8 | 0 | 8 |
| `RMI` | [RMI] Rural Marine Industrial | `RMI` | 21 | 0 | 4 | 1 |
| `RFS` | [RFS] Rural Freeway Service | `RFS` | 20 | 1 | 11 | 7 |
| `RC` | [RC] Rural Center | `RC` | 20 | 7 | 13 | 0 |
| `SSB` | [SSB] Small-Scale Business | `SSB` | 15 | 6 | 7 | 2 |
| `URP-OS` | [URP-OS] Urban Reserve Public Open Space | `SEDRO WOOLLEY UGA` | 6 | 1 | 4 | 0 |
| `SRT` | [SRT] Small-Scale Recreation & Tourism | `SRT` | 5 | 0 | 0 | 4 |

## LLM Guidance

- If the user says "residential zones only", do not hard-code only `LIKE 'R%'`.
- Prefer a zoning evidence expression using both `zoning_code_short` and
  `zoning_label`.
- For incorporated parcels represented by `CITY`, require matching city/place and
  residential land-use evidence.
- When zoning is uncertain, keep the user's requested asset class as the hard filter
  and expose zoning compatibility in `match_reasons` or score.
- Select `zoning_code_short`, `zoning_label`, and `comp_plan_lud` when zoning is a
  prompt requirement so the UI/evals can verify the match.
