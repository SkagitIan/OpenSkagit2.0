# Skagit Zoning AI Query Spec

Purpose: compact, AI-friendly zoning reference that can be parsed into database filters, lookup tables, and query rules.

This is not intended to be a public-facing legal summary. Treat it as a machine-readable working layer that maps jurisdiction, zoning district, land use, and permission status into normalized query logic.

---

## 1. Normalized Permission Codes

| Code | Meaning | Query Meaning |
|---|---|---|
| P | Permitted outright | Use is allowed in the zone |
| AC | Accessory use | Use is allowed only when accessory to a principal use |
| AD | Administrative special use permit | Use may be allowed after administrative approval |
| HE | Hearing Examiner special use permit | Use may be allowed after Hearing Examiner approval |
| CUP | Conditional use permit | Use may be allowed after conditional use review |
| X | Prohibited | Use is not allowed |
| BLANK | Not listed / unknown | Treat as prohibited unless local code says otherwise |

Suggested DB field:

```python
allowed_status = models.CharField(
    max_length=10,
    choices=[
        ("P", "Permitted"),
        ("AC", "Accessory"),
        ("AD", "Administrative Review"),
        ("HE", "Hearing Examiner"),
        ("CUP", "Conditional Use"),
        ("X", "Prohibited"),
        ("UNKNOWN", "Unknown / Not Parsed"),
    ],
)
```

---

## 2. Core Data Model

Use long-format rows, not wide zoning tables.

```yaml
zoning_use_rule:
  jurisdiction: skagit_county
  source_chapter: "SCC 14.11"
  source_table: "Table 14.11.020-1"
  zone_code: "RVR"
  zone_name: "Rural Village Residential"
  use_category: "Residential Uses"
  use_name: "Single-family residence"
  normalized_use_key: "single_family_residence"
  local_status: "P"
  normalized_status: "P"
  source_url: "https://www.codepublishing.com/WA/SkagitCounty/..."
  notes: ""
```

Minimum useful table:

| Field | Example |
|---|---|
| jurisdiction | skagit_county |
| source_table | Table 14.11.020-1 |
| zone_code | RVR |
| use_name | Single-family residence |
| normalized_use_key | single_family_residence |
| status | P |
| notes |  |

---

## 3. Query Rule Logic

### Find zones where a use is allowed outright

```python
ZoningUseRule.objects.filter(
    jurisdiction="skagit_county",
    normalized_use_key="restaurant",
    normalized_status="P",
)
```

### Find zones where a use is possible but needs review

```python
ZoningUseRule.objects.filter(
    jurisdiction="skagit_county",
    normalized_use_key="restaurant",
    normalized_status__in=["AD", "HE", "CUP"],
)
```

### Find zones where a use is not allowed

```python
ZoningUseRule.objects.filter(
    jurisdiction="skagit_county",
    normalized_use_key="restaurant",
    normalized_status__in=["X", "UNKNOWN"],
)
```

### Score development friction

```python
STATUS_SCORE = {
    "P": 100,
    "AC": 70,
    "AD": 55,
    "CUP": 45,
    "HE": 35,
    "X": 0,
    "UNKNOWN": 0,
}
```

---

## 4. Jurisdiction Keys

```yaml
jurisdictions:
  skagit_county:
    display_name: "Skagit County"
    code_source: "Code Publishing"
    zoning_title: "Title 14 Unified Development Code"
  anacortes:
    display_name: "Anacortes"
    code_source: "Municipal Code"
    zoning_title: "Title 19 Unified Development Code"
  burlington:
    display_name: "Burlington"
    code_source: "Municipal Code"
    zoning_title: "Title 17 Zoning"
  mount_vernon:
    display_name: "Mount Vernon"
    code_source: "Municipal Code"
    zoning_title: "Title 17 Zoning"
  sedro_woolley:
    display_name: "Sedro-Woolley"
    code_source: "Municipal Code"
    zoning_title: "Title 17 Zoning"
  concrete:
    display_name: "Concrete"
    code_source: "Municipal Code"
    zoning_title: "Title 19 Development Regulations"
  hamilton:
    display_name: "Hamilton"
    code_source: "Municipal Code / Ordinances"
    zoning_title: "Needs source confirmation"
  la_conner:
    display_name: "La Conner"
    code_source: "Municipal Code"
    zoning_title: "Title 15 Unified Development Code"
  lyman:
    display_name: "Lyman"
    code_source: "Town zoning code"
    zoning_title: "Needs source confirmation"
```

---

## 5. Skagit County Rural Mixed-Use Zones

Source table: `Table 14.11.020-1 Allowed Uses in the Rural Mixed-Use Zones`

Zone columns from source:

```yaml
skagit_county_rural_mixed_use_zones:
  RI: Rural Intermediate
  RRv: Rural Reserve
  RVR: Rural Village Residential
  RC: Rural Center
  RVC: Rural Village Commercial
  RVC_Alger: Rural Village Commercial - Alger
  OSRSI: Open Space of Regional/Statewide Importance
```

---

## 6. Starter Use Rules From Screenshot

These are starter rows transcribed from the provided screenshot. Verify against the source code before relying on them for final production output.

| jurisdiction | source_table | use_category | normalized_use_key | use_name | RI | RRv | RVR | RC | RVC | RVC_Alger | OSRSI |
|---|---|---|---|---|---|---|---|---|---|---|---|
| skagit_county | Table 14.11.020-1 | Residential Uses | single_family_residence | Single-family residence | P | P | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | accessory_dwelling_unit | Accessory dwelling unit | P | P | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | middle_housing_2_to_4_units | Middle housing (2—4 units) | X | X | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | cohousing_card | Co-housing as part of a CaRD | P | P | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | loft_living_quarters | Loft living quarters | X | X | X | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | owner_operator_caretaker_quarters | Owner operator/caretaker quarters | X | X | X | AC | AC | AC | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | emergency_housing | Emergency housing | X | X | X | X | P | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | emergency_shelter | Emergency shelter | X | X | X | X | P | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | manufactured_mobile_home_park | Manufactured or mobile home park | X | X | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | permanent_supportive_housing | Permanent supportive housing | X | X | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | residential_accessory_use | Residential accessory use | P | P | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | seasonal_worker_housing | Seasonal worker housing | HE | HE | X | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | transitional_housing | Transitional housing | X | X | P | X | P | X | X |
| skagit_county | Table 14.11.020-1 | Residential Uses | temporary_manufactured_home | Temporary manufactured home | P | P | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | animal_clinic_hospital | Animal clinic/hospital | HE | HE | X | HE | AD | AD | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | animal_preserve | Animal preserve | X | HE | X | X | X | X | HE |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | asphalt_concrete_batching_recycling_temporary | Asphalt/concrete batching or recycling, temporary | X | HE | X | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | bed_and_breakfast | Bed and breakfast | AD | AD | AD | P | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | business_professional_office | Business/professional office | X | X | X | X | P | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | display_gardens | Display gardens | X | HE | X | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | family_day_care_provider | Family day care provider | P | P | P | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | group_care_facility | Group care facility | HE | X | X | HE | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | group_care_facility_adult | Group care facility, adult | HE | X | X | X | AD | AD | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | home_based_business_1 | Home-Based Business 1 | P | P | P | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | home_based_business_2 | Home-Based Business 2 | AD | AD | AD | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | home_based_business_3 | Home-Based Business 3 | HE | HE | HE | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | kennel_boarding | Kennel, boarding | HE | HE | HE | AD | AD | AD | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | kennel_day_use | Kennel, day-use | HE | AD | HE | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | kennel_limited | Kennel, limited | HE | HE | HE | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | laundromat | Laundromat | X | X | X | X | X | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | limited_event_venues | Limited event venues | AD | AD | AD | AD | AD | X | AD |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | marijuana_retail_facility | Marijuana retail facility | X | X | X | AD | AD | AD | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | marina_20_slips_or_less | Marina, ≤20 slips | HE | X | X | X | HE | X | HE |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | marina_more_than_20_slips | Marina, >20 slips | X | X | X | X | X | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | mini_storage | Mini-storage | X | X | X | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | mortuary | Mortuary | HE | X | X | X | HE | X | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | outpatient_medical_health_care_service | Outpatient medical and health care service | X | X | HE | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | overnight_lodging_related_services | Overnight lodging and related services for visitors to the rural area | X | X | X | X | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | restaurant | Restaurant | X | X | X | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | small_retail_service_business | Small retail and service business | X | X | X | P | P | P | X |
| skagit_county | Table 14.11.020-1 | Commercial/Retail Uses | small_scale_production_manufacture | Small-scale production or manufacture | X | X | X | X | AD | AD | X |

---

## 7. Same Data As YAML

This format is easier for an AI/code parser than a visual table.

```yaml
rules:
  - jurisdiction: skagit_county
    source_table: Table 14.11.020-1
    use_category: Residential Uses
    use_name: Single-family residence
    normalized_use_key: single_family_residence
    zones:
      RI: P
      RRv: P
      RVR: P
      RC: X
      RVC: X
      RVC_Alger: X
      OSRSI: X

  - jurisdiction: skagit_county
    source_table: Table 14.11.020-1
    use_category: Commercial/Retail Uses
    use_name: Restaurant
    normalized_use_key: restaurant
    zones:
      RI: X
      RRv: X
      RVR: X
      RC: P
      RVC: P
      RVC_Alger: P
      OSRSI: X

  - jurisdiction: skagit_county
    source_table: Table 14.11.020-1
    use_category: Commercial/Retail Uses
    use_name: Small retail and service business
    normalized_use_key: small_retail_service_business
    zones:
      RI: X
      RRv: X
      RVR: X
      RC: P
      RVC: P
      RVC_Alger: P
      OSRSI: X
```

---

## 8. Practical OpenSkagit Query Examples

### User asks:
"Can I put a restaurant on this parcel?"

Required parcel facts:

```yaml
parcel:
  jurisdiction: skagit_county
  zoning_code: RC
```

Query:

```python
rule = ZoningUseRule.objects.get(
    jurisdiction=parcel.jurisdiction,
    zone_code=parcel.zoning_code,
    normalized_use_key="restaurant",
)

if rule.normalized_status == "P":
    answer = "Likely allowed outright."
elif rule.normalized_status in ["AD", "HE", "CUP"]:
    answer = "Possibly allowed, but permit review is required."
else:
    answer = "Likely not allowed in this zone."
```

### User asks:
"Show me parcels where small retail is easiest."

Query intent:

```python
ZoningUseRule.objects.filter(
    normalized_use_key="small_retail_service_business",
    normalized_status="P",
)
```

Then join to parcel table:

```python
Parcel.objects.filter(
    jurisdiction__in=allowed_jurisdictions,
    zoning_code__in=allowed_zone_codes,
)
```

---

## 9. Better Final Shape For Production

Use three tables.

```text
Jurisdiction
- id
- name
- source_url

Zone
- id
- jurisdiction_id
- zone_code
- zone_name

ZoningUseRule
- id
- jurisdiction_id
- zone_id
- use_category
- use_name
- normalized_use_key
- local_status
- normalized_status
- source_table
- source_url
- notes
```

For AI search, also create aliases.

```yaml
use_aliases:
  restaurant:
    - restaurant
    - cafe
    - diner
    - food service
    - eating place
  accessory_dwelling_unit:
    - ADU
    - accessory apartment
    - mother-in-law unit
    - detached accessory dwelling
  small_retail_service_business:
    - small retail
    - shop
    - boutique
    - service business
    - neighborhood retail
  business_professional_office:
    - office
    - professional office
    - business office
    - real estate office
    - insurance office
  mini_storage:
    - self storage
    - storage units
    - mini storage
```

---

## 10. Next Extraction Target

Instead of compiling every jurisdiction into one giant human table, extract one jurisdiction at a time into this row format:

```csv
jurisdiction,source_table,zone_code,use_category,use_name,normalized_use_key,status,notes
skagit_county,Table 14.11.020-1,RC,Commercial/Retail Uses,Restaurant,restaurant,P,
skagit_county,Table 14.11.020-1,RVC,Commercial/Retail Uses,Restaurant,restaurant,P,
skagit_county,Table 14.11.020-1,RI,Commercial/Retail Uses,Restaurant,restaurant,X,
```

This is the format that should feed OpenSkagit queries.
