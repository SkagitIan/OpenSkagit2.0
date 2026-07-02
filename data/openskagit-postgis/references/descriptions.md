# OpenSkagit Human-Readable Data Descriptions

Use this reference when explaining what OpenSkagit fields mean, designing AI-to-SQL
context, or writing opportunity queries that should return readable labels alongside
raw assessor/GIS codes.

## Core Rule

Return raw values and descriptions together whenever a field is coded.

Raw codes keep the query reproducible. Descriptions make the answer usable by humans.
Do not infer meanings from raw codes when a mapped description exists.

## Description Sources

### `code_mappings`

Canonical lookup table for readable assessor descriptions.

Columns: `category`, `code`, `description`, `source`, `created_at`, `updated_at`.

Known categories:

- `land_use`: assessor land-use codes, such as `111` for SFR inside city and `911`
  for undeveloped incorporated land.
- `utilities`: utility tokens, such as public water, well, septic, sewer, and power.
- `neighborhood`: assessor neighborhood/revaluation area labels.
- `improvement_type`: improvement segment/type codes, such as `MA`, `DECK`, `AGAR`,
  `CCP`, `BMF`, and `UF2`.
- `improvement_class`: construction/class/quality codes, such as `MSA`, `MSG`,
  `MSF`, and plus/minus variants.
- `condition`: condition codes, such as `A`, `G`, `VG`, `F`, `E`, `L`, and `P`.

Use `code_mappings` when a readable column is missing, stale, or the query needs a
lookup table.

## Preferred Description Columns

Prefer existing normalized readable columns when present.

| Table | Code column | Human-readable column |
| --- | --- | --- |
| `assessor_rollup` | `land_use_code` | `land_use_description` |
| `assessor_rollup` | `neighborhood_code_id` | `neighborhood_description` |
| `assessor_rollup` | `utilities_codes` | `utilities_description` |
| `improvements` | `imprv_det_type_cd` | `imprv_det_type_description` |
| `improvements` | `imprv_det_class_cd` | `imprv_det_class_description` |
| `improvements` | `condition_cd` | `condition_description` |

Example parcel description query:

```sql
SELECT
    p.parcel_number,
    concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
    p.land_use AS raw_land_use,
    ar.land_use_code,
    COALESCE(ar.land_use_description, land_use_map.description) AS land_use_description,
    ar.utilities_codes,
    ar.utilities_description,
    ar.neighborhood_code_id,
    ar.neighborhood_description,
    z.zone_id,
    z.zone_name,
    z.waza_general,
    z.waza_specific
FROM skagit_parcels p
LEFT JOIN assessor_rollup ar ON ar.parcel_number = p.parcel_number
LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
LEFT JOIN code_mappings land_use_map
  ON land_use_map.category = 'land_use'
 AND land_use_map.code = ar.land_use_code
WHERE p.parcel_number = %s
LIMIT 1
```

## Display Strings That Already Contain Meaning

`skagit_parcels.land_use` often stores code plus label:

```text
(111) HOUSEHOLD, SFR, INSIDE CITY
(112) HOUSEHOLD SFR, WITH A SECONDARY DETACHED UNIT
(180) MANUFACTURED HOMES
(911) UNDEVELOPED LAND INCORPORATED
```

Use it for display, but parse the code for filtering or joins:

```sql
split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code
```

## Zoning Description Fields

`parcel_primary_zoning` and `parcel_zoning` contain source zoning and normalized WAZA
labels.

| Column | Meaning |
| --- | --- |
| `zone_id` | Local/source zoning code |
| `zone_name` | Local/source zoning name |
| `waza_general` | Broad normalized zone group |
| `waza_specific` | More specific normalized zone class |
| `reference_url` | Source/reference page for zoning |

In human-facing answers, show local labels plus normalized labels when possible.

## Opportunity Labels

Explain opportunity labels as screening signals, not determinations.

- "Vacant buildable" means the parcel passed current filters for vacant/low-building
  value, land use, and zoning; it is not a permit or entitlement finding.
- "Possible lot split" means acreage and zoning make the parcel worth review; it is
  not an approved subdivision yield.
- "Teardown candidate" means land/building/value/age signals suggest review; it is not
  a physical inspection result.
- "Delinquent tax pressure" means public tax-statement data shows unpaid or late tax
  signals; scrape freshness and payment timing matter.

## AI-To-SQL Context Guidance

When building an AI SQL writer for OpenSkagit:

1. Load schema and code-description context before generating SQL.
2. Translate the request into tables, joins, filters, metrics, and assumptions.
3. Resolve readable descriptions before answering with raw codes.
4. Use parameterized SQL with `%s` placeholders for user-provided values.
5. Restrict execution to read-only `SELECT`/`WITH`, or explicitly guarded temp-table
   analysis when the app allows it.
6. Return SQL plus assumptions, readable labels, and reality checks.
7. Mention empty result sets, small samples, null-heavy fields, duplicate-sale risk,
   stale sync data, and zoning/land-use approximation limits.

## Quick Human-Readable Result Checklist

For parcel result rows, include:

- `parcel_number`
- address or city context
- raw code where it matters
- readable description from a `*_description` column or `code_mappings.description`
- zoning source label and normalized WAZA label when zoning matters
- a short caveat when the label is an analytical screen rather than a legal fact
