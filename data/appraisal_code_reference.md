# Skagit County Appraisal Code Reference

Condensed from: SFR guide, CDT guide, Mobile Home guide, Barn Book.
Use this to interpret improvement `type`, `class`, and detail feature codes in
parcel/improvement data. Not a full reproduction of the source PDFs — summary only.

## Quality/Class codes (Marshall & Swift ratings, apply across all methods)
| Code | Meaning |
|---|---|
| MSL | Low |
| MSF | Fair |
| MSA | Average |
| MSG | Good |
| MSVG | Very Good |
| MSE | Excellent |

`+` suffix (e.g. MSG+) = available on MAIN/UPPER floor segments only, SFR method.

## Actual Age vs Effective Age
- **Actual Year Built / Actual Age**: literal construction date.
- **Effective Year Built / Effective Age**: adjusted for condition/remodeling —
  drives depreciation, not the literal age. A gut-remodeled old home can have a much
  younger effective age than actual age.

## SFR (Single Family Residential) — Type/Improvement codes
| Code | Meaning |
|---|---|
| MA | Main living area, single level home (or home w/ basement) |
| MA-SPLIT | Upper floor area, split-entry design |
| MA-TRI | Main + upper levels, tri-level design |
| MA1.5(F/U) | Main floor, 1.5-story home; F/U = top level finished/unfinished |
| MA2 | Main level, 2-story design |
| MA2.5(F/U) | Main floor, 2.5-story home |
| UF1.5(F/U) | Upper floor, 1.5-story home |
| UF2 | Upper floor, 2-story design |
| UF2.5(F/U) | Upper floor, 2.5-story home |
| AGAR / AG1.5 / AG2 | Attached garage (plain / w. sloped room above / w. full room above) |
| DGAR / DG1.5 / DG2 | Detached garage (same variants) |
| GBI | Built-in garage area |
| CARP | Carport |
| LOFT | Area above garage |
| GARFIN | Finished area attached to garage |
| BMU / BML / BMF / BMG / BMT | Basement: unfinished / low finish / fully finished / garage / tri-level lower |
| CP / CCP / DECK / CWP | Concrete patio / covered concrete patio / wood deck / covered wood deck |
| SUN | Glass sunroom (frame+glass only in base) |
| ENP | Enclosed/covered porch |
| SAUNA, HOT TUB | Standalone specialty details |
| MPS | Multi-purpose shed |
| RC | Roof cover only (no walls) |
| LT | Lean-to |
| C-S / CSL | Cabin/studio / cabin sleeping loft |
| BBQ / OFP / OS / OHT | Built-in barbecue / outdoor fireplace / outdoor sink / outdoor heater |

## CDT (Condo/Duplex/Townhouse, up to 4 units — 5+ uses Commercial M&S 352)
Same MA/UF type codes as SFR but sub-class uses **END-YYYY** or **INSIDE-YYYY**
to indicate unit position within the building (shared-wall properties).
Additional: AGAR, DGAR, GBI, CARP, BMU/BML/BMF/BMG, CP/CCP/DECK/CWP, SUN, SAUNA.

## Mobile / Manufactured Homes (Method M)
| Code | Meaning |
|---|---|
| SW | Single-wide main area (2018+ cost tables) |
| MW | Multi-wide main area (2018+ cost tables) |
| SW4/SW6/MW4/MW6 | Pre-2018 equivalents |
| PM | Park model |
| ENP, DECK, DGAR | Same meaning as SFR |
State Code on mobile homes: e.g. **DW** = Double Wide. Primary Use e.g. **180** = Mobile Homes.

## Barn Book (Type I — Misc. Improvement, State Code MISC)
| Code | Meaning |
|---|---|
| ARNA | Arena |
| BUNK | Bunker silo |
| FDB | Feeder barn |
| FSB | Free stall barn |
| GPB | General purpose building |
| GPBFIN | GPB finished area (stand-alone finished building/area) |
| GREENH | Greenhouse |
| HRC | Hay/roof cover |
| HSTB | Hobby stable |
| LT | Lean-to |
| LFT | Loft (used with Loft Barn or GPB) |
| LB | Loft barn |
| MSHD | Machine shed |
| LAGOON | Manure lagoon |
| MCB | Metal component building (steel/light commercial) |
| MLKB | Milk barn (holding pen) |
| MP | Milk parlor |
| PS | Potato storage |
| PLH | Poultry laying house |
| DOCK | Dock |
| SWIM RAFT | Swim raft |

## Fireplace codes (SFR/CDT/PM)
| Code | Meaning |
|---|---|
| S1/S2/S3 | 1 masonry fireplace, chimney extends 1/2/3+ stories |
| S1-STEEL/S2-STEEL/S3-STEEL | Same but steel-vented (wood chase) |
| D1/D2/D3 | 2 fireplaces, shared chimney, 1/2/3+ stories |
| DIRECT VENT | Fireplace/stove venting straight through wall or roof |

## Plumb Fix baseline counts (varies by method + quality)
Rough-in always adds 3 (kitchen sink, water heater, washer). Bath type counts:
MB=5, FB=3, 3QB=3, HB=2, Laundry/prep sink=1.
SFR baseline by quality: MSL=6, MSF=7, MSA=9, MSG=12, MSVG=15, MSE=18.
CDT baseline by quality: MSF=7, MSA=8, MSG=9, MSVG=10, MSE=12.

## Interior Finish climate note
"Mild Climate" applies to units/homes built **pre-1970**; otherwise "Moderate Climate."

## DOR Primary Use / Land Use codes (updated 8-28-2019)
Numeric codes seen in improvement/property data that are NOT improvement type/method
codes — these are Washington State DOR property use classifications, applied at the
property level. Do not confuse with imprv_det_type_cd values like AGAR/MA2/DECK.

| Code | Meaning |
|---|---|
| 110 | Household SFR, outside city (with improvements) |
| 111 | Household SFR, inside city (with improvements) |
| 112 | Household SFR w/ separate detached unit |
| 113 | Household SFR w/ 2+ detached units |
| 120 | Household, 2-4 attached units |
| 130 | Household, 5+ units |
| 140 | Condo residential |
| 150 | Mobile home parks |
| 160 | Hotels, motels |
| 170 | Institutional lodging |
| 180 | Mobile homes |
| 181 | MH leased property |
| 182 | MH land, 2+ units (same ownership) |
| 185 | MH with detached SFR 2nd unit |
| 190 | Vacation and cabin |
| 210-360 | Manufacturing/industrial (food, textile, lumber, furniture, paper, printing, chemicals, petroleum, rubber/plastic, leather, stone/clay/glass, primary metal, fabricated metal, prof/scientific instruments, log dump) |
| 390 | Land zoned industrial with residence |
| 410-490 | Transportation/communication/utilities (rail, motor vehicle, aircraft, marine, ROW, parking, communications, utilities/dike/drain, other) |
| 500 | Condos, non-residential |
| 510-590 | Wholesale/retail trade (building materials, general merchandise, food, auto, apparel, furniture, eating/drinking, other) |
| 610-691 | Services (finance/insurance/real estate, personal, business, repair incl. marine, professional, contract construction, government, education, misc. incl. marine wharfs/marinas) |
| 710-790 | Cultural/recreation (nature exhibits, public assembly, amusements, recreation, resorts/camps, parks, cemetery, other incl. churches) |
| 810-890 | Agriculture/resource (non-classified, ag-related, open space/farm/ag [was 982], fishing, mining, marijuana grow, classified/designated timber [was 831/984], other resource production) |
| 910 | Unimproved land (county) |
| 911 | Unimproved land (inside city) |
| 912 | Unimproved land, multi-family |
| 920 | Trees |
| 930 | Water areas |
| 940 | Open space [was 981] |
| 941 | Farm & ag conservation |
| 970 | Condo moorage |
