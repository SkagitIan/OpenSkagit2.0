# Opportunity Search Ontology

This document is the source-of-truth vocabulary for Opportunity AI Search. Use it
when translating user prompts into SQL, writing eval cases, repairing failed evals,
and deciding whether a returned parcel is the requested asset class.

Primary source docs:

- `data/appraisal_code_reference.md`
- `data/schema_dump.md`
- `opportunity/r2_search.py` R2 guardrails
- `opportunity/ai_search.py` prompt/result filters
- OpenSkagit PostGIS skill references for schema, codes, and readable descriptions

## Core Principles

1. Preserve the user's noun. If the user asks for homes, land, commercial parcels,
   mobile home parks, condos, public/civic uses, or recreation lots, find that asset
   first. Zoning compatibility is secondary.
2. Keep property-use codes separate from improvement-detail codes.
   DOR land-use codes describe the parcel/use. Improvement codes describe building
   segments, quality, condition, and physical features.
3. Use current parcel facts for current asset exclusions. Historical sale buyer or
   seller text can explain provenance, but it should not make a current private
   parcel fail an owner/use exclusion by itself.
4. Return evidence columns. If a filter depends on quality, utilities, exemptions,
   improvement count, sales age, geometry, or land-use code, select the evidence or
   include it in `match_reasons`.
5. Treat outputs as screening signals, not legal determinations. Zoning, comp-plan,
   public/civic flags, and opportunity labels require follow-up review.

## Source-Of-Truth Fields

### Parcel Identity

- R2 derived files: `parcel_number`
- `assessor.parquet`: `"Parcel Number"`
- `sales.parquet`: `"Parcel Number"`
- `improvements.parquet`: `ParcelNumber`
- `land.parquet`: `ParcelNumber`

Use `TRIM()` when joining raw parcel IDs.

### Land Use / DOR Property Use

Preferred field:

- `derived/parcel_search*.parquet.land_use`

The value is a full label such as `(111) HOUSEHOLD, SFR, INSIDE CITY`, not a bare
number. Extract the code before filtering:

```sql
regexp_extract(COALESCE(ps.land_use, ''), '^\((\d+)\)', 1)
```

Use `TRY_CAST(NULLIF(..., '') AS INTEGER)` for numeric ranges.

Do not compare `land_use IN ('911')` or `TRIM(land_use) = '180'`.

### Improvements

Preferred summaries:

- `derived/parcel_search*.parquet.improvement_building_count`
- `derived/parcel_search*.parquet.primary_actual_year_built`
- `derived/parcel_search*.parquet.oldest_actual_year_built`
- `derived/parcel_search*.parquet.primary_effective_year_built`
- `derived/parcel_search*.parquet.total_garage_area`
- `derived/parcel_search*.parquet.total_living_area`

Raw evidence:

- `improvements.parquet.imprv_det_type_cd`
- `improvements.parquet.imprv_det_class_cd`
- `improvements.parquet.condition_cd`
- `improvements.parquet.actual_year_built`
- `improvements.parquet.effective_yr_blt`

Use raw improvements when an eval or prompt needs exact segment, quality, or
condition evidence.

### Utilities And Exemptions

Utilities and exemptions live in `assessor.parquet`.

- Utilities: `"Utilities"`
- Exemptions: `"Exemptions"`

`derived/parcel_search.parquet` does not contain `utilities` or `exemptions`.

For utilities-present prompts, join `assessor.parquet`, select
`TRIM(a."Utilities") AS utilities`, and filter non-empty/non-`NONE` tokens.

For no-utilities prompts, select the same evidence and require empty, null, or
`NONE`-style utility evidence.

For no-exemptions prompts, select `TRIM(a."Exemptions") AS exemptions` and require
empty/null evidence.

Known utility tokens include:

- `PWR`: power
- `PWR-U`: underground power
- `SEP`: septic
- `SEW`: sewer
- `WTR-P`: public water
- `WTR-W`: well water
- `NONE`: no listed utilities

### Sales

Preferred derived fields:

- `years_since_last_valid_sale`
- `last_valid_sale_date`
- `last_valid_sale_price`
- `valid_sale_count`
- `has_valid_sale`

For "no sale in N years" prompts, `years_since_last_valid_sale >= N` is strong
evidence. Missing valid-sale evidence can be acceptable only when the eval/prompt
explicitly allows "no valid sale record" to count as old/no-sale.

### Geometry And Maps

Preferred fields:

- `has_geometry`
- `gis_x`
- `gis_y`

Only use `gis_x/gis_y` for maps when they are valid WGS84 longitude/latitude
bounds. Otherwise preserve the existing no-geometry flag.

## Asset Classes

### SFR / Single-Family Residential

Use for prompts like:

- single family homes
- SFR
- houses
- existing residential dwellings, when not asking for mobile/manufactured homes

Primary land-use codes:

- `110`: Household SFR outside city
- `111`: Household SFR inside city
- `112`: Household SFR with separate detached unit
- `113`: Household SFR with two or more detached units

Do not include mobile/manufactured codes `180` or `185` for SFR unless the prompt
explicitly asks for mobile/manufactured homes.

Dwelling improvement evidence may include:

- `MA`, `MA-SPLIT`, `MA-TRI`, `MA1.5F`, `MA1.5U`, `MA2`, `MA2.5F`, `MA2.5U`
- `UF1.5F`, `UF1.5U`, `UF2`, `UF2.5F`, `UF2.5U`
- dwelling basement/living-area indicators such as `BMF`, `BMU`, `BMG`, `BML`

Garage/remodel signals may include:

- `AGAR`, `AG1.5`, `AG2`
- `DGAR`, `DG1.5`, `DG2`
- `GBI`, `CARP`, `LOFT`, `GARFIN`
- summary field `total_garage_area`

### Multi-Family / Small Residential Income

Primary land-use codes:

- `120`: Household, 2-4 attached units
- `130`: Household, 5+ units

Use `120` for duplex/triplex/fourplex style prompts. Use `130` for larger
apartment/multifamily prompts.

Do not satisfy a multi-family prompt with SFR codes unless the prompt is about
conversion potential and the result explains that it is not existing multi-family.

### Condominiums

Primary land-use code:

- `140`: Condo residential

Condo/CDT improvement records may use the same MA/UF type codes as SFR but with
sub-class labels such as `END-YYYY` or `INSIDE-YYYY`. Do not treat condo intent as
SFR intent.

Non-residential condo/moorage codes:

- `500`: Condos, non-residential
- `970`: Condo moorage

### Mobile / Manufactured Homes

Mobile/manufactured property-use codes:

- `150`: Mobile home parks
- `180`: Mobile homes / manufactured homes
- `181`: MH leased property
- `182`: MH land, 2+ units, same ownership
- `185`: MH with detached SFR second unit

Important distinction:

- `150` is a mobile home park asset.
- `180`, `181`, `182`, and `185` are individual/mobile-manufactured home asset
  families and should not satisfy "mobile home parks only" prompts.

Mobile/manufactured improvement codes include:

- `SW`, `MW`
- `SW4`, `SW6`, `MW4`, `MW6`
- `PM`

`MH LEASED PROPERTY` is not bare land. It may lack normal main-area improvement
records but still represents leased manufactured-home occupancy.

### Commercial / Retail / Service

Primary DOR code families:

- `510-590`: Wholesale/retail trade
- `610-691`: Services

Use these for commercial, retail, restaurant, office/service, and redevelopment
prompts unless the user asks for industrial, lodging, or public/civic assets.

Do not satisfy commercial prompts by merely excluding SFR. Positively filter to the
commercial/service code family or clear commercial/service labels.

### Industrial / Manufacturing

Primary DOR code family:

- `210-360`: Manufacturing/industrial

Related code:

- `390`: Land zoned industrial with residence

Use `390` carefully: it can be relevant to industrial redevelopment but is not a
pure industrial asset without additional zoning/use evidence.

### Transportation / Communication / Utility

Primary DOR code family:

- `410-490`: Transportation, communication, and utility uses

This includes rail, motor vehicle, aircraft, marine, right-of-way, parking,
communications, utilities, dike/drain, and related uses.

Do not confuse utility property-use codes with assessor utility-service tokens such
as `PWR`, `SEP`, or `WTR-P`.

### Agriculture / Resource / Timber

Primary DOR code family:

- `810-890`: Agriculture/resource, ag-related, open space/farm/ag, fishing,
  mining, marijuana grow, classified/designated timber, and other resource
  production

Related codes:

- `920`: Trees
- `940`: Open space
- `941`: Farm and ag conservation

Resource/ag prompts should use acreage, land-use code, and zoning/comp-plan as
separate evidence. Natural resource zoning is a risk/context flag, not by itself a
property-use code.

### Bare / Unimproved / Vacant Land

Core land-use codes:

- `910`: Unimproved land, county
- `911`: Unimproved land, inside city
- `912`: Unimproved land, multi-family

Supporting open-space/resource codes may be relevant depending on the prompt:

- `940`: Open space
- `941`: Farm and ag conservation
- selected `810-890` resource codes

Required no-improvement evidence:

- `COALESCE(ps.improvement_building_count, 0) = 0`

Land-use labels alone are not enough for no-improvements prompts. Always select
`improvement_building_count` when filtering on no improvements.

Exclude from private bare-land/recreation-lot prompts unless explicitly requested:

- mobile/manufactured leased or occupied codes `181`, `182`, `185`
- condo/common-area/moorage codes `140`, `500`, `970`
- public/civic/government/school/church/cemetery/park uses
- zero-acre rows when acreage matters
- rows without valid map geometry when the prompt asks for mappable lots
- existing residential dwelling evidence

### Recreation

There are two distinct recreation meanings.

#### Cultural/Recreation Businesses Or Public Uses

Primary DOR code family:

- `710-790`: Cultural/recreation uses

This family can include nature exhibits, public assembly, amusements, recreation,
resorts/camps, parks, cemetery, churches, and related uses.

Use it for prompts asking for recreation properties, parks, camps, resorts, public
assembly, or recreation businesses.

#### Private Bare Recreation Lots

Use unimproved/open-space land evidence plus exclusions. Relevant codes often
include:

- `910`
- `911`
- `940`
- `941`
- selected non-public recreation-like land rows when supported by prompt/context

Do not let DOR `710-790` alone satisfy "bare recreation lot" prompts; those are
often active/public/business/civic uses.

### Public / Civic / Institutional

Common DOR codes/families:

- `670`: Governmental services
- `680`: Schools
- `610-691`: Services can include government, education, and institutional uses
- `710-790`: Can include public assembly, parks, cemeteries, churches

For "private investment" style prompts, public/civic signals are usually exclusion
or risk flags. For explicit public/civic prompts, they are positive evidence.

Use current owner, current land-use, current zoning/comp-plan, and current address
context for owner/use exclusions. Historical sale buyer/seller text is not enough
to classify the current parcel as public/civic.

### Water / Moorage

Common codes:

- `930`: Water areas
- `970`: Condo moorage

These should not be converted into generic land opportunity rows unless the prompt
explicitly asks for water/moorage assets.

## Quality, Condition, And Age

### Quality / Class Codes

Quality lives in `improvements.parquet.imprv_det_class_cd`.

Codes:

- `MSL`: Low
- `MSF`: Fair
- `MSA`: Average
- `MSG`: Good
- `MSVG`: Very Good
- `MSE`: Excellent

Rules:

- Low quality means `TRIM(i.imprv_det_class_cd) = 'MSL'`.
- Fair quality means `TRIM(i.imprv_det_class_cd) = 'MSF'`.
- Average quality means `TRIM(i.imprv_det_class_cd) = 'MSA'`.
- Do not satisfy exact average quality by merely excluding `MSL`.
- Select `quality_codes` or include the quality code in `match_reasons`.

### Condition Codes

Condition lives in `improvements.parquet.condition_cd` or derived
`condition_codes`.

Condition values are a separate family from quality:

- `L`
- `F`
- `A`
- `G`
- `VG`
- `E`
- other raw variants may exist

Do not filter `condition_codes` for `MSL`, `MSF`, or `MSA`. Those are quality/class
codes, not condition codes.

### Actual Age vs Effective Age

- Actual year/age is literal construction timing.
- Effective year/age is adjusted for condition/remodeling and depreciation.

For "old homes", "built before", or historic-era prompts, prefer actual-year fields:

- `primary_actual_year_built`
- `oldest_actual_year_built`
- `improvements.actual_year_built`

For remodel/depreciation/condition prompts, effective-year fields can be useful but
should be labeled as effective age, not literal age.

Do not invent `year_built`. Use listed schema fields.

## Place And Jurisdiction Semantics

### Countywide

"Skagit County" means the dataset scope. Do not filter `city_name` or
`situs_city_state_zip` for "skagit".

### Named Cities And Places

Use current parcel place fields:

- `city_name`
- `situs_city_state_zip`
- `inside_city_limits`
- zoning/comp-plan fields as context

For named place searches, never use `inside_city_limits = TRUE` as a standalone OR
branch. That matches every incorporated city.

For "immediate unincorporated vicinity", postal city in `situs_city_state_zip` may
be better than `inside_city_limits`.

Known spelling normalization should include:

- Sedro Woolley / Sedro-Woolley
- Marbelmount -> Marblemount

### Flood Plain

"Flood plain" is a condition or exclusion, not a place. Do not filter
`city_name` or `situs_city_state_zip` for "flood". If no floodplain field is listed
in the allowed schema, state the limitation in assumptions or match reasons rather
than inventing a hard filter.

## Query And Eval Contracts

### SQL Generation Contract

Generated SQL must:

- be one read-only `SELECT` or `WITH` query
- read only approved R2 parquet paths with `read_parquet()`
- return normalized `parcel_number`
- avoid semicolons, mutation/admin statements, arbitrary paths, URLs, `INSTALL`,
  `LOAD`, `SECRET`, and `ATTACH`
- qualify columns in joined queries
- quote mixed-case or space-containing raw columns such as `"Parcel Number"`,
  `"Utilities"`, and `"Exemptions"`
- use `TRIM()` for raw code/id joins and equality filters

### Evidence Contract

When a result depends on a rule, return the evidence:

- land-use filters: return `land_use` and/or `land_use_code`
- utility filters: return `utilities`
- exemption filters: return `exemptions`
- no-improvement filters: return `improvement_building_count`
- quality filters: return `quality_codes`
- age filters: return actual/effective year fields used
- sales filters: return `years_since_last_valid_sale`
- geometry filters: return `has_geometry` or valid `gis_x/gis_y`
- nuanced ranking: return `score` or `match_reasons`

### Eval Design Contract

Prefer row-level expectations over brittle SQL text expectations when behavior can
be verified from returned evidence.

Good SQL pattern expectations:

- required source table, such as `assessor.parquet` for utilities/exemptions
- required source column, such as `"Utilities"` or `imprv_det_class_cd`
- known safety traps, such as forbidding `ps.utilities`

Risky SQL pattern expectations:

- requiring a particular alias name
- requiring `match_reasons` when feature labels already expose evidence
- requiring exact row-count maxima for broad countywide prompts unless the limit is
  part of the desired behavior

Use eval failures to classify the likely repair layer:

- SQL/schema guardrail
- generation guidance
- prompt/result filter
- row hydration
- eval expectation
- source data ambiguity

## Common Traps

- `ps.utilities` does not exist in `derived/parcel_search.parquet`.
- `exemptions` does not exist in `derived/parcel_search.parquet`.
- `acres`, `land_use`, and similarly named columns become ambiguous in joins; qualify
  with aliases.
- DOR land-use codes are not improvement type codes.
- `MSL`, `MSF`, and `MSA` are quality/class codes, not condition codes.
- `180`/`185` manufactured/mobile homes are not SFR for strict SFR prompts.
- `150` mobile home parks are not individual mobile homes.
- `181` MH leased property is not bare land.
- DOR `710-790` recreation/cultural uses are not automatically private bare
  recreation lots.
- Historical buyer/seller text should not drive current owner/use exclusions.
- `inside_city_limits = TRUE OR city_name = ...` is too broad.
- "Skagit County" and "flood plain" are not city-name filters.
