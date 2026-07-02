# OpenSkagit Assessor Code Reference

Snapshot source: live `code_mappings` table inspected on 2026-06-23. Use this when translating assessor, land, utility, neighborhood, condition, and improvement codes.

`code_descriptions` and `primary_use_codes` were empty at inspection time; `code_mappings` contained the usable lookup data.

## How To Use Codes

- Join `code_mappings` on `(category, code)` when SQL should explain a coded field.

- Improvement records already include normalized description columns: `imprv_det_type_description`, `imprv_det_class_description`, and `condition_description`. Prefer those columns when present.

- Normalize lookup codes with trim/upper behavior. Some fields include padded values, plus/minus variants, or raw values not covered by `code_mappings`.

- For `skagit_parcels.land_use`, values are often formatted like `(111) HOUSEHOLD, SFR, INSIDE CITY`; parse the numeric code when joining to `code_mappings.category = 'land_use'`.

- For `skagit_parcels.utilities`, values may be comma-separated and prefixed with `*`; split and clean tokens before joining to `code_mappings.category = 'utilities'`.


## Lookup Categories

- `condition`: 8 mappings
- `improvement_class`: 61 mappings
- `improvement_type`: 386 mappings
- `land_use`: 85 mappings
- `neighborhood`: 493 mappings
- `utilities`: 7 mappings

## Improvement Fields

| Field | Meaning | Lookup | Notes |
| --- | --- | --- | --- |
| `improvements.imprv_det_type_cd` | Improvement segment/type code, such as `MA`, `DECK`, `CCP` | `code_mappings.category = 'improvement_type'` | `MA` is the common main-area improvement code. Use description column if available. |
| `improvements.imprv_det_class_cd` | Construction/quality class, such as `MSA`, `MSG`, `MSF` | `code_mappings.category = 'improvement_class'` | `MSA` means manufactured/system average quality in current mappings. |
| `improvements.condition_cd` | Condition, such as `A`, `G`, `VG`, `F` | `code_mappings.category = 'condition'` | Most values map cleanly; rare raw variants like `A+` may not. |
| `improvements.imprv_val` / `imprv_val_num` | Improvement value | none | Use numeric `_num` when available. |
| `improvements.tot_living_area` / `living_area_num` | Living area | none | Use numeric `_num` when available. |

### SQL: Explain Improvement Codes

```sql
SELECT
    i.parcelnumber AS parcel_number,
    i.imprv_id,
    i.segment_id,
    i.imprv_det_type_cd,
    COALESCE(i.imprv_det_type_description, type_map.description) AS type_description,
    i.imprv_det_class_cd,
    COALESCE(i.imprv_det_class_description, class_map.description) AS class_description,
    i.condition_cd,
    COALESCE(i.condition_description, condition_map.description) AS condition_description,
    i.imprv_val_num,
    i.living_area_num
FROM improvements i
LEFT JOIN code_mappings type_map
  ON type_map.category = 'improvement_type'
 AND type_map.code = upper(trim(i.imprv_det_type_cd))
LEFT JOIN code_mappings class_map
  ON class_map.category = 'improvement_class'
 AND class_map.code = upper(trim(i.imprv_det_class_cd))
LEFT JOIN code_mappings condition_map
  ON condition_map.category = 'condition'
 AND condition_map.code = upper(trim(i.condition_cd))
WHERE i.parcelnumber = :parcel_number
ORDER BY i.imprv_id, i.segment_id;
```

## Common Live Values

### `improvements.imprv_det_type_cd`
| Value | Count |
| --- | ---: |
| `DECK` | 38089 |
| `CCP` | 29614 |
| `CWP` | 27558 |
| `MA` | 27195 |
| `MPS` | 23743 |
| `AGAR` | 19370 |
| `CP` | 18823 |
| `UF2` | 9803 |
| `MA2` | 8939 |
| `GPB` | 8789 |
| `DGAR` | 8590 |
| `LT` | 8256 |
| `CARP` | 6078 |
| `ENP` | 5909 |
| `UF1.5F` | 5848 |
| `BMF` | 5661 |
| `MA1.5F` | 5325 |
| `MW` | 4596 |
| `GBI` | 3734 |
| `RC` | 3655 |
| `BMG` | 2701 |
| `MSHD` | 2654 |
| `BMU` | 2628 |
| `POR` | 2013 |
| `LOFT` | 1954 |
| `C-S` | 1920 |
| `SW` | 1448 |
| `BML` | 1229 |
| `DOCK` | 1208 |
| `CPOR` | 1197 |

### `improvements.imprv_det_class_cd`
| Value | Count |
| --- | ---: |
| `MSA` | 170296 |
| `MSF` | 66219 |
| `MSG` | 36790 |
| `MSF+` | 8401 |
| `MSA+` | 7106 |
| `*` | 7020 |
| `MSVG` | 6398 |
| `MSL` | 1893 |
| `MSE` | 1596 |
| `MSG+` | 1424 |
| `4` | 548 |
| `5` | 251 |
| `3` | 235 |
| `MSVG+` | 231 |
| `6` | 46 |
| `MSL+` | 42 |
| `2` | 35 |
| `F` | 23 |
| `A` | 11 |
| `G` | 9 |
| `0` | 6 |
| `S5` | 6 |
| `TX3` | 6 |
| `E` | 5 |
| `L` | 5 |
| `S4` | 5 |
| `VG` | 5 |
| `DX3` | 4 |
| `FX4` | 4 |
| `MSVG-` | 4 |

### `improvements.condition_cd`
| Value | Count |
| --- | ---: |
| `A` | 147947 |
| `G` | 87980 |
| `VG` | 26748 |
| `F` | 24765 |
| `E` | 11992 |
| `*` | 4952 |
| `L` | 2445 |
| `P` | 93 |
| `AR` | 76 |
| `GR` | 39 |
| `FR` | 26 |
| `VGR` | 26 |
| `A+` | 24 |
| `DEPRE` | 24 |
| `FAIR` | 10 |
| `AV` | 9 |
| `G+` | 4 |
| `VG_` | 4 |
| `+` | 2 |
| `2001` | 2 |
| `23` | 2 |
| `ER` | 2 |
| `MSA` | 2 |
| `1976` | 1 |
| `1980` | 1 |
| `5` | 1 |
| `A+_` | 1 |
| `A-` | 1 |
| `D` | 1 |
| `E+` | 1 |

### `improvements.building_style`
| Value | Count |
| --- | ---: |
| `1` | 91356 |
| `2` | 41325 |
| `1.5` | 28615 |
| `1BF` | 22364 |
| `DW` | 19466 |
| `OUTBL` | 18517 |
| `MISC` | 13408 |
| `1BU` | 7175 |
| `F1` | 6876 |
| `SE` | 6689 |
| `1.5BU` | 6333 |
| `C` | 6268 |
| `SW` | 5792 |
| `2BF` | 5369 |
| `DX` | 5344 |
| `1.5BF` | 4734 |
| `TL` | 3479 |
| `2BU` | 2812 |
| `FX` | 1674 |
| `TW` | 1460 |
| `A1` | 1432 |
| `PM` | 1377 |
| `TX` | 1069 |
| `2.5` | 1039 |
| `AP` | 836 |
| `TH` | 797 |
| `Y` | 607 |
| `1B` | 455 |
| `3` | 394 |
| `2.5BU` | 275 |

### `improvements.constructionstyle`
| Value | Count |
| --- | ---: |
| `DECK` | 964 |
| `CCP2` | 444 |
| `TD` | 390 |
| `CWP2` | 335 |
| `CCP1` | 251 |
| `CP` | 246 |
| `CWP1` | 223 |
| `CD` | 197 |
| `ATT` | 167 |
| `FD` | 145 |
| `CWP (COMP)` | 137 |
| `CWP (FG/MTL/VIN)` | 73 |
| `CCP (COMP)` | 72 |
| `PATIO` | 70 |
| `WOOD FRAME` | 70 |
| `METAL FRAME` | 43 |
| `WP` | 28 |
| `CCP (FG/MTL/VIN)` | 21 |
| `PIPE FRAME` | 9 |
| `SCREEN ROOM (COMP)` | 9 |
| `SCREEN ROOM (FG/MTL/VIN)` | 9 |
| `SWIM RAFT` | 5 |
| `DOCK` | 2 |
| `21100` | 1 |

### `improvements.foundation`
| Value | Count |
| --- | ---: |
| `CONC` | 26786 |
| `C` | 8453 |
| `HILLSIDE - MODERATE` | 3815 |
| `P` | 1828 |
| `CB` | 1784 |
| `SKIRTING - MTL/VIN (HORZ)` | 1636 |
| `SKIRTING - WOOD` | 1585 |
| `SKIRTING - CONC BLOCK` | 1584 |
| `SKIRTING - MTL/VIN (VERT)` | 441 |
| `SKIRTING - PRECAST PANELS` | 392 |
| `SKIRTING - SIDING` | 383 |
| `HILLSIDE - STEEP` | 327 |
| `DECK` | 135 |
| `S` | 131 |
| `SKIRTING - BRK/STN VENEER` | 95 |
| `CWP` | 67 |
| `CCP` | 22 |
| `CP` | 21 |
| `MODERATE CLIMATE` | 15 |
| `SKIRTING - MTL/VIN (PATTERN)` | 7 |
| `WOOD` | 5 |
| `METAL` | 1 |

### `improvements.exteriorwall`
| Value | Count |
| --- | ---: |
| `SIDING` | 62111 |
| `PLYWOOD` | 36463 |
| `BKEN` | 7394 |
| `METAL/VINYL SIDING` | 5229 |
| `SHAKE/SHINGLE` | 4597 |
| `S` | 2090 |
| `METAL` | 1718 |
| `GALV METAL` | 1188 |
| `STUCCO` | 985 |
| `VINYL` | 747 |
| `CONC BLOCK` | 585 |
| `MASONRY VENEER` | 374 |
| `LOG` | 347 |
| `FIBERGLASS` | 299 |
| `BRICK` | 279 |
| `NO END WALLS` | 255 |
| `CEMENT FIBER` | 226 |
| `POLY` | 169 |
| `GLASS` | 78 |
| `EIFS` | 36 |
| `FBRGLS/PVC-VINYL` | 35 |
| `STAY-IN-PLACE Forming` | 21 |
| `POLY-CARB (GRNHSE)` | 17 |
| `PLASTIC` | 16 |
| `BRICK/STONE VENEER` | 6 |

### `improvements.roofcovering`
| Value | Count |
| --- | ---: |
| `COMP` | 87129 |
| `BKEN` | 30847 |
| `GALV METAL` | 7721 |
| `BU` | 2557 |
| `METAL` | 2448 |
| `COMP - ROLL` | 1580 |
| `SHAKE` | 1414 |
| `FBRGLS/VINYL` | 1161 |
| `WS` | 931 |
| `TILE` | 829 |
| `GALV` | 477 |
| `WOOD SHINGLE` | 315 |
| `POLY` | 276 |
| `FG` | 210 |
| `CONCRETE TILE` | 185 |
| `CLAY TILE` | 148 |
| `GLASS` | 38 |
| `COPPER` | 9 |
| `SLATE` | 7 |
| `CT` | 4 |
| `VINYL` | 3 |

### `improvements.heatingcooling`
| Value | Count |
| --- | ---: |
| `FA` | 31691 |
| `HP` | 6375 |
| `BB` | 5239 |
| `EW` | 2848 |
| `W/F` | 1902 |
| `FA, AC` | 865 |
| `NONE` | 827 |
| `BBHW` | 700 |
| `HOT WATER - RADIANT` | 700 |
| `SPACE HEATER` | 609 |
| `N` | 487 |
| `ELECTRIC - RADIANT` | 247 |
| `WOOD STOVE` | 227 |
| `SH` | 178 |
| `R` | 55 |
| `WALL (Sauna)` | 51 |
| `AC` | 25 |
| `FLOOR (Sauna)` | 23 |
| `GREENHOUSE VENT` | 22 |
| `w/f` | 9 |
| `HUM` | 5 |
| `OUTDOOR - BRACKET MOUNT` | 3 |
| `HEAT` | 2 |

### `land.land_type`
| Value | Count |
| --- | ---: |
| `CLEARED` | 80346 |
| `WOODED/BRUSH` | 17676 |
| `TIMBER` | 6058 |
| `CONVERTED DELETED LAND SEGMENT` | 1865 |
| `CONVERTED LAND SEGMENT` | 401 |
| `TIDELAND` | 124 |
| `WET` | 109 |
| `HOMESITE` | 15 |
| `WET WOODED` | 10 |
| `GRAVEL PIT` | 6 |
| `SITE IMPROVEMENTS` | 3 |
| `BAKER VIEW` | 1 |
| `SWAMP` | 1 |

### `land.appr_meth`
| Value | Count |
| --- | ---: |
| `ACREAGE` | 57766 |
| `LOT` | 35153 |
| `SQUARE FOOT` | 6232 |
| `Front Foot - Average` | 4185 |
| `FLAT; FLAT PRICED PER LOT` | 15 |

### `skagit_parcels.land_use`
| Value | Count |
| --- | ---: |
| `(111) HOUSEHOLD, SFR, INSIDE CITY` | 20394 |
| `(110) HOUSEHOLD SFR OUTSIDE CITY` | 15037 |
| `(910) UNIMPROVED LAND UNINCORPORATED` | 6982 |
| `(830) CURRENT USE FARM AND AG` | 4652 |
| `(180) MANUFACTURED HOMES` | 3464 |
| `(0) Personal Property` | 3223 |
| `(190) VACATION AND CABIN` | 2442 |
| `(880) FORESTLAND UNDER RCW 84.33` | 2416 |
| `(920) TREES` | 2409 |
| `(911) UNDEVELOPED LAND INCORPORATED` | 2287 |
| `(181) MH LEASED PROPERTY` | 2022 |
| `(450) HIGHWAY & STREET RIGHT OF WAY` | 1886 |
| `(140) CONDO RESIDENTIAL` | 1801 |
| `(112) HOUSEHOLD SFR, WITH A SECONDARY DETACHED UNIT` | 1253 |
| `(970) CONDO MOORAGE` | 1181 |
| `(120) HOUSEHOLD, 2-4 UNITS` | 1052 |
| `(930) WATER AREAS` | 1026 |
| `(850) MINING ACTIVITIES & RELATED SERVICES` | 737 |
| `(690) MISCELLANEOUS SERVICES` | 711 |
| `(840) FISHING ACTIVITIES & RELATED SERVICES` | 683 |
| `(760) PARKS` | 557 |
| `(480) UTILITIES (DIKE & DRAIN PROPERTY)` | 447 |
| `(670) GOVERNMENTAL SERVICES` | 392 |
| `(650) PROFESSIONAL SERVICES` | 374 |
| `(940) OPEN SPACE/OPEN SPACE` | 355 |
| `(130) HOUSEHOLD, 5+ UNITS` | 332 |
| `(430) AIRCRAFT TRANSPORTATION` | 291 |
| `(810) AGRICULTURE, NON-CLASSIFIED O/S` | 279 |
| `(740) RECREATIONAL ACTIVITIES` | 272 |
| `(680) EDUCATION SERVICES (SCHOOLS)` | 266 |

### `skagit_parcels.proptype`
| Value | Count |
| --- | ---: |
| `R` | 78276 |
| `P` | 3317 |
| `M` | 2045 |

### `skagit_parcels.hasseptic`
| Value | Count |
| --- | ---: |
| `False` | 83638 |

### `skagit_parcels.utilities`
| Value | Count |
| --- | ---: |
| `*SEW, PWR, WTR-P` | 22971 |
| `*SEP, PWR, WTR-P` | 9115 |
| `*SEP, PWR, WTR-W` | 8855 |
| `*SEW, WTR-P` | 4899 |
| `*SEP, WTR-P` | 3851 |
| `*WTR-P` | 956 |
| `*PWR, WTR-P` | 596 |
| `*PWR` | 239 |
| `*PWR, WTR-W` | 167 |
| `*NONE` | 113 |
| `*SEW` | 113 |
| `*SEW, PWR, WTR-W` | 91 |
| `*SEP, WTR-W` | 71 |
| `*SEP` | 69 |
| `*WTR-W` | 38 |
| `SEW, PWR WTR-P` | 29 |
| `*SEP, PWR` | 25 |
| `*SEW, PWR` | 22 |
| `'SEP PWR WTR-P` | 5 |
| `WTR-P,PWR-U,SEW` | 4 |
| `*SEW, WTR-W` | 2 |
| `WTR,PWR,SEW` | 2 |
| `PWR-U,WTR-P,SEP` | 1 |
| `PWR-U,WTR-W,SEP` | 1 |
| `PWR,WTR,SEW` | 1 |
| `SEW.PWR-U,WTR-P` | 1 |

## `condition` Mappings
| Code | Description | Source |
| --- | --- | --- |
| `*` | Unknown | built-in |
| `A` | Average | built-in |
| `E` | Excellent | built-in |
| `F` | Fair | built-in |
| `G` | Good | built-in |
| `L` | Low | built-in |
| `P` | Poor | built-in |
| `VG` | Very good | built-in |

## `improvement_class` Mappings
| Code | Description | Source |
| --- | --- | --- |
| `0` | CABIN | impsegclass.csv |
| `0.94` | 0 CLASS FOR 1994 | impsegclass.csv |
| `1` | SUB STAN | impsegclass.csv |
| `1.94` | CLASS 1 FOR 1994 | impsegclass.csv |
| `2` | LOW | impsegclass.csv |
| `22` | TEST | impsegclass.csv |
| `2.94` | CLASS 2 FOR 1994 | impsegclass.csv |
| `3` | FAIR | impsegclass.csv |
| `3.94` | CLASS 3 FOR 1994 | impsegclass.csv |
| `4` | AVG | impsegclass.csv |
| `4.94` | CLASS 4 REVAL YEAR 94 | impsegclass.csv |
| `4S` | CLASS 4 SINGLE WIDE | impsegclass.csv |
| `5` | GOOD | impsegclass.csv |
| `5.94` | CLASS 5 FOR 1995 | impsegclass.csv |
| `6` | V-GOOD | impsegclass.csv |
| `6.94` | CLASS 6 FOR 1994 | impsegclass.csv |
| `7` | EXCELLENT | impsegclass.csv |
| `7.94` | CLASS 7 FOR 1994 | impsegclass.csv |
| `8` | SPECIAL | impsegclass.csv |
| `8.94` | CLASS 8 FOR 1994 | impsegclass.csv |
| `AVG-P` | AVERAGE PLUS | impsegclass.csv |
| `D3` | CLASS 3 DOUBLE WIDE MOBILE | impsegclass.csv |
| `D4` | CLASS 4 DOUBLE WIDE | impsegclass.csv |
| `D5` | CLASS 5 DOUBLE WIDE | impsegclass.csv |
| `D6` | CLASS 6 DOUBLE WIDE | impsegclass.csv |
| `D7` | CLASS 7 DOUBLE WIDE | impsegclass.csv |
| `D8` | CLASS 8 DOUBLE WIDE | impsegclass.csv |
| `DX3` | DUPLEX CLASS 3 | impsegclass.csv |
| `DX4` | DUPLEX CLASS 4 | impsegclass.csv |
| `DX5` | DUPLEX CLASS 5 | impsegclass.csv |
| `DX6` | DUPLEX CLASS 6 | impsegclass.csv |
| `FX3` | FOURPLEX CL 3 | impsegclass.csv |
| `FX4` | FOURPLEX CL 4 | impsegclass.csv |
| `FX5` | FOURPLEX CL 5 | impsegclass.csv |
| `FX6` | FOURPLEX CL 6 | impsegclass.csv |
| `L` | LARGE | impsegclass.csv |
| `M` | MEDIUM | impsegclass.csv |
| `MR5` | MULTI RES CLASS 5 | impsegclass.csv |
| `MSA` | M/S AVERAGE QUALITY | impsegclass.csv |
| `MSE` | M/S EXCELLANT QUALITY | impsegclass.csv |
| `MSF` | M/S FAIR QUALITY | impsegclass.csv |
| `MSG` | M/S GOOD QUALITY | impsegclass.csv |
| `MSL` | M/S LOW QUALITY | impsegclass.csv |
| `MSVG` | M/S VERY GOOD QUALITY | impsegclass.csv |
| `PM4` | PARK MODEL CLASS 4 | impsegclass.csv |
| `PM5` | PARK MODEL CLASS 5 | impsegclass.csv |
| `PM6` | PARK MODEL CLASS 6 | impsegclass.csv |
| `PM7` | PARK MODEL CLASS 7 | impsegclass.csv |
| `R33` | S | impsegclass.csv |
| `RM5` | MULTI-RES CLASS 5 | impsegclass.csv |
| `S` | SMALL | impsegclass.csv |
| `S3` | CLASS 3 SINGLE WIDE | impsegclass.csv |
| `S4` | CLASS 4 SINGLE WIDE | impsegclass.csv |
| `S5` | CLASS 5 SINGLE WIDE | impsegclass.csv |
| `S6` | CLASS 6 SINGLE WIDE | impsegclass.csv |
| `S7` | CLASS 7 SINGLE WIDE | impsegclass.csv |
| `SP` | SP | impsegclass.csv |
| `TX3` | TRIPLEX CL 3 | impsegclass.csv |
| `TX4` | TRIPLEX CL 4 | impsegclass.csv |
| `TX5` | TRIPLEX CL 5 | impsegclass.csv |
| `TX6` | TRIPLEX CL 6 | impsegclass.csv |

## `utilities` Mappings
| Code | Description | Source |
| --- | --- | --- |
| `NONE` | No listed utilities | built-in |
| `PWR` | Power | built-in |
| `PWR-U` | power-underground | utilities.csv |
| `SEP` | septic | utilities.csv |
| `SEW` | sewer | utilities.csv |
| `WTR-P` | water-public | utilities.csv |
| `WTR-W` | water-well | utilities.csv |

## `land_use` Mappings
| Code | Description | Source |
| --- | --- | --- |
| `110` | HOUSEHOLD SFR OUTSIDE CITY | landuse.csv |
| `111` | HOUSEHOLD SFR INSIDE CITY | landuse.csv |
| `112` | HOUSEHOLD SFR, WITH A SECONDARY DETACHED UNIT | landuse.csv |
| `113` | HOUSEHOLD SFR, WITH TWO OR MORE DETACHED UNITS | landuse.csv |
| `120` | HOUSEHOLD, 2-4 UNITS | landuse.csv |
| `130` | HOUSEHOLD, 5+ UNITS | landuse.csv |
| `140` | CONDO RESIDENTIAL | landuse.csv |
| `150` | MOBILE HOME PARKS | landuse.csv |
| `160` | HOTELS, MOTELS | landuse.csv |
| `170` | INSTITUTIONAL LODGING | landuse.csv |
| `180` | MANUFACTURED HOMES | landuse.csv |
| `181` | MH LEASED PROPERTY | landuse.csv |
| `182` | MOBILE HOMES, LAND WITH 2 OR MORE MOBILES | landuse.csv |
| `185` | MH WITH DETACHED SFR SECOND UNIT | landuse.csv |
| `190` | VACATION AND CABIN | landuse.csv |
| `210` | FOOD AND KINDRED PRODUCTS | landuse.csv |
| `220` | TEXTILE MILL PRODUCTS | landuse.csv |
| `230` | APPAREL/FINISHED PROD FROM FABRIC/LEATHER/SIMILAR | landuse.csv |
| `240` | LUMBER AND WOOD PRODUCTS | landuse.csv |
| `250` | FURNITURE AND FIXTURES | landuse.csv |
| `260` | PAPER & ALLIED PRODUCTS | landuse.csv |
| `270` | PRINTING & PUBLISHING | landuse.csv |
| `280` | CHEMICALS | landuse.csv |
| `290` | PETROLEUM REFINING & RELATED INDUSTRY | landuse.csv |
| `300` | RUBBER AND MISC PLASTIC PRODUCTS | landuse.csv |
| `310` | LEATHER AND LEATHER PRODUCTS | landuse.csv |
| `320` | STONE, CLAY & GLASS PRODUCTS | landuse.csv |
| `330` | PRIMARY METAL PRODUCTS | landuse.csv |
| `340` | FABRICATED METAL PRODUCTS | landuse.csv |
| `350` | PROF SCIENTIFIC/CONTROL INSTR/PHOTO & OPTICAL GDS | landuse.csv |
| `360` | LOG DUMP | landuse.csv |
| `390` | LAND ZONED INDUSTRIAL WITH RESIDENCE | landuse.csv |
| `410` | RAILROAD TRANSPORTATION | landuse.csv |
| `420` | MOTOR VEHICLE TRANSPORTATION | landuse.csv |
| `430` | AIRCRAFT TRANSPORTATION | landuse.csv |
| `440` | MARINE CRAFT TRANSPORTATION | landuse.csv |
| `450` | HIGHWAY AND STREET RIGHT OF WAY | landuse.csv |
| `460` | AUTOMOBILE PARKING | landuse.csv |
| `470` | COMMUNICATIONS | landuse.csv |
| `480` | UTILITIES (DIKE & DRAIN PROPERTIES) | landuse.csv |
| `490` | OTHER TRANSPORT/COMMUNICATION/UTILITIES NOT ELSEWHERE | landuse.csv |
| `500` | CONDOMINIUMS OTHER THAN RESIDENTIAL | landuse.csv |
| `510` | WHOLESALE TRADE | landuse.csv |
| `520` | RETAIL TRADE/BUILDING MATERIAL/HARDWARE/FARM EQUIP | landuse.csv |
| `530` | RETAIL TRADE, GENRAL MERCHANDISE | landuse.csv |
| `540` | RETAIL TRADE, FOOD | landuse.csv |
| `550` | RETAIL/AUTO/TIRES/MARINECRAFT/AIRCRAFT & ACCESS | landuse.csv |
| `560` | RETAIL TRADE, APPAREL & ACCESSORIES | landuse.csv |
| `570` | RETAIL TRADE, FURNITURE, HOME FURNISH. & EQUIP | landuse.csv |
| `580` | RETAIL TRADE, EATING & DRINKING | landuse.csv |
| `590` | OTHER RETAIL TRADES | landuse.csv |
| `610` | FINANCE, INSURANCE & REAL ESTATE | landuse.csv |
| `620` | PERSONAL SERVICES | landuse.csv |
| `630` | BUSINESS SERVICES | landuse.csv |
| `640` | REPAIR SERVICES | landuse.csv |
| `650` | PROFESSIONAL SERVICES | landuse.csv |
| `660` | CONTRACT CONSTRUCTION SERVICES | landuse.csv |
| `670` | GOVERNMENTAL SERVICES | landuse.csv |
| `680` | EDUCATION SERVICES (SCHOOLS) | landuse.csv |
| `690` | MISC SERVICES | landuse.csv |
| `691` | MARINE RELATED SERVICES | landuse.csv |
| `710` | CULTURAL ACTIVITES & NATURE EXHIBITS | landuse.csv |
| `720` | PUBLIC ASSEMBLY | landuse.csv |
| `730` | AMUSEMENTS | landuse.csv |
| `740` | RECREATIONAL ACTIVITES | landuse.csv |
| `750` | RESORTS AND GROUP CAMPS | landuse.csv |
| `760` | PARKS | landuse.csv |
| `770` | CEMETERY | landuse.csv |
| `790` | OTHER CULTURAL/ENTERTAIN/RECRATIONAL & CHURCHES | landuse.csv |
| `810` | AGRICULTURE NON CLASSIFIED O/S | landuse.csv |
| `820` | AGRICULTURE RELATED ACTIVITIES | landuse.csv |
| `830` | CURRENT USE FARM AND AG UNDER RCW 84.34 | landuse.csv |
| `840` | FISHING ACTIVITES & RELATED SERVICES | landuse.csv |
| `850` | MINING ACTIVIES & RELATED SERVICES | landuse.csv |
| `860` | MARIJUANA GROW OPERATION | landuse.csv |
| `880` | FORESTLAND UNDER RCW 84.33 | landuse.csv |
| `890` | OTHER RESOURCE PRODUCTION | landuse.csv |
| `910` | UNIMPROVED LAND | landuse.csv |
| `911` | UNDEVELOPED LAND INCORPORATED | landuse.csv |
| `912` | UNDEVELOPED LAND 2-4 FAMILY | landuse.csv |
| `920` | TREES | landuse.csv |
| `930` | WATER AREAS | landuse.csv |
| `940` | OPEN SPACE/OPEN SPACE UNDER RCW 84.34 | landuse.csv |
| `941` | CURRENT USE OPEN SPACE FARM & AG CONSERVATION | landuse.csv |
| `970` | CONDO MOORAGE | landuse.csv |

## `improvement_type` Mappings
| Code | Description | Source |
| --- | --- | --- |
| `10` | MISC/COMMERCIAL | impsegtype.csv |
| `300` | APARTMENT | impsegtype.csv |
| `301` | ARMORY | impsegtype.csv |
| `302` | AUDITORIUM | impsegtype.csv |
| `303` | AUTOMOBILE SHOWROOM | impsegtype.csv |
| `304` | BANK | impsegtype.csv |
| `305` | BARN | impsegtype.csv |
| `306` | BOWLING ALLEY | impsegtype.csv |
| `308` | CHURCH W SUNDAY SCHOOL | impsegtype.csv |
| `309` | CHURCH | impsegtype.csv |
| `310` | CITY CLUB | impsegtype.csv |
| `311` | CLUB HOUSE | impsegtype.csv |
| `313` | HOSPITAL,CONVALESCENT | impsegtype.csv |
| `314` | COUNTRY CLUB | impsegtype.csv |
| `315` | CREAMERY | impsegtype.csv |
| `316` | DAIRY | impsegtype.csv |
| `317` | DAIRY SALES BLDG | impsegtype.csv |
| `318` | DEPARTMENT STORE | impsegtype.csv |
| `319` | DISCOUNT STORE | impsegtype.csv |
| `320` | DISPENSARY | impsegtype.csv |
| `321` | DORMITORY | impsegtype.csv |
| `322` | FIRE STATION (STAFF) | impsegtype.csv |
| `323` | FRATERNAL BUILDING | impsegtype.csv |
| `324` | FRATERNITY HOUSE | impsegtype.csv |
| `325` | GARAGE,SERVICE | impsegtype.csv |
| `326` | GARAGE,STORAGE | impsegtype.csv |
| `327` | GOVERNMENTAL BUILDING | impsegtype.csv |
| `328` | STORAGE HANGAR | impsegtype.csv |
| `329` | HANGAR, MAINT AND OFFICE | impsegtype.csv |
| `330` | HOME FOR THE ELDERLY | impsegtype.csv |
| `331` | HOSPITAL | impsegtype.csv |
| `334` | INDUSTRIAL MFG (OBSOLETE) | impsegtype.csv |
| `335` | JAIL -CORRECTIONAL FACILITY | impsegtype.csv |
| `336` | LAUNDROMAT | impsegtype.csv |
| `337` | LIBRARY | impsegtype.csv |
| `338` | LOFT | impsegtype.csv |
| `339` | LUMBER STORAGE HORIZONTAL | impsegtype.csv |
| `340` | MARKET | impsegtype.csv |
| `341` | OFFICE,MEDICAL | impsegtype.csv |
| `342` | MORTUARY | impsegtype.csv |
| `343` | MOTEL | impsegtype.csv |
| `344` | OFFICE BUILDING | impsegtype.csv |
| `345` | PARKING STRUCTURE | impsegtype.csv |
| `346` | POST OFFICE | impsegtype.csv |
| `347` | POULTRY HOUSE | impsegtype.csv |
| `348` | RECTORY | impsegtype.csv |
| `349` | FAST FOOD RESTAURANT | impsegtype.csv |
| `350` | RESTAURANT | impsegtype.csv |
| `352` | MULTIPLE RESIDENCE - LOW RISE | impsegtype.csv |
| `353` | RETAIL STORE | impsegtype.csv |
| `355` | FINE ARTS & CRAFTS | impsegtype.csv |
| `356` | CLASSROOM | impsegtype.csv |
| `357` | COMMONS | impsegtype.csv |
| `358` | GYMNASIUM | impsegtype.csv |
| `359` | LECTURE CLASSROOM | impsegtype.csv |
| `360` | MEDIA CENTER (ELEM, SECONDAY SCHOOL) | impsegtype.csv |
| `361` | MANUAL ARTS BLDG (ELEM, SECONARY SCHOOL) | impsegtype.csv |
| `362` | MULTIPURPOSE BUILDING | impsegtype.csv |
| `363` | PHYSICAL ED BLDG (ELEM, SECONDARY SCHOOL) | impsegtype.csv |
| `364` | SCIENCE CLASSROOMS (ELEM, SECONDARY SCHOOL) | impsegtype.csv |
| `365` | ELEMENTARY SCHOOL(ENTIRE) | impsegtype.csv |
| `366` | SECONDARY SCHOOL(ENTIRE) | impsegtype.csv |
| `367` | ARTS AND CRAFTS (COLLEGE) | impsegtype.csv |
| `368` | CLASSROOM (COLLEGE) | impsegtype.csv |
| `369` | COMMONS (COLLEGE) | impsegtype.csv |
| `370` | GYMNASIUM (COLLEGE) | impsegtype.csv |
| `371` | LECTURE HALL (COLLEGE) | impsegtype.csv |
| `372` | LIBRARY (COLLEGE) | impsegtype.csv |
| `374` | MULTI-PURPOSE BLDG (COLLEGE) | impsegtype.csv |
| `377` | COLLEGE (ENTIRE) | impsegtype.csv |
| `378` | STABLE | impsegtype.csv |
| `379` | THEATER, LIVE STAGE | impsegtype.csv |
| `380` | THEATER, CINEMA | impsegtype.csv |
| `381` | HOSPITAL,VETERINARY | impsegtype.csv |
| `384` | BARBER SHOP | impsegtype.csv |
| `386` | WAREHOUSE,MINI | impsegtype.csv |
| `387` | WAREHOUSE,TRANSIT | impsegtype.csv |
| `388` | UNDERGROUND PARKING STRUCTURE | impsegtype.csv |
| `389` | SHED,EQUIPMENT | impsegtype.csv |
| `390` | LUMBER STORAGE VERTICAL | impsegtype.csv |
| `391` | MATERIAL STORAGE BLDG | impsegtype.csv |
| `392` | INDUSTRIAL ENGINEERING BLDG | impsegtype.csv |
| `393` | LABOR DORMITORY | impsegtype.csv |
| `394` | TRANSIENT LABOR CABIN | impsegtype.csv |
| `395` | POTATO STORAGE | impsegtype.csv |
| `396` | HOG BARN | impsegtype.csv |
| `397` | SHEEP BARN | impsegtype.csv |
| `398` | FRUIT PACKING BARN | impsegtype.csv |
| `399` | CATTLE SHED | impsegtype.csv |
| `403` | SHOWER BLDG | impsegtype.csv |
| `404` | UTILITY BUILDING | impsegtype.csv |
| `405` | SKATING RINK | impsegtype.csv |
| `406` | WAREHOUSE,STORAGE | impsegtype.csv |
| `407` | WAREHOUSE,DISTRIBUTION | impsegtype.csv |
| `409` | T-HANGAR | impsegtype.csv |
| `410` | AUTOMOTIVE CENTER | impsegtype.csv |
| `412` | NEIGHBORHOOD SHOPPING CENTER | impsegtype.csv |
| `413` | COMMUNITY SHOPPING CENTER | impsegtype.csv |
| `414` | REGIONAL SHOPPING CENTER | impsegtype.csv |
| `416` | TENNIS CLUB, INDOOR | impsegtype.csv |
| `417` | HANDBALL-RACQUETBALL CLUB | impsegtype.csv |
| `418` | HEALTH CLUB | impsegtype.csv |
| `419` | CONVENIENCE MARKET | impsegtype.csv |
| `42` | GAS STATION | impsegtype.csv |
| `420` | BULK FERTILIZER STORAGE | impsegtype.csv |
| `421` | GRAIN STORAGE | impsegtype.csv |
| `423` | GARAGE,MINI-LUBE | impsegtype.csv |
| `424` | GROUP CARE HOME | impsegtype.csv |
| `426` | DAY CARE CENTER | impsegtype.csv |
| `427` | FIRE STATION,VOLUNTEER | impsegtype.csv |
| `430` | HOG SHED | impsegtype.csv |
| `431` | OUTPATIENT SURGICAL CENTER | impsegtype.csv |
| `432` | RESTROOM BUILDING | impsegtype.csv |
| `434` | SELF-SERVE CAR WASH | impsegtype.csv |
| `435` | DRIVE-THROUGH CAR WASH | impsegtype.csv |
| `436` | AUTOMATIC CAR WASH | impsegtype.csv |
| `440` | MILKHOUSE | impsegtype.csv |
| `441` | COCKTAIL LOUNGE | impsegtype.csv |
| `442` | BAR - TAVERN | impsegtype.csv |
| `443` | CENTRAL BANK | impsegtype.csv |
| `444` | DENTAL OFFICE/CLINC | impsegtype.csv |
| `446` | MARKET,SUPER | impsegtype.csv |
| `447` | COLD STORAGE FACILITIES | impsegtype.csv |
| `448` | COLD STORAGE, FARM | impsegtype.csv |
| `451` | MULTIPLE RES SR CITIZEN | impsegtype.csv |
| `453` | INDUSTRIAL FLEX BLDG | impsegtype.csv |
| `454` | SHELL, INDUSTRIAL | impsegtype.csv |
| `455` | AUTO DEALERSHIP, COMPLETE | impsegtype.csv |
| `456` | TOOL SHED | impsegtype.csv |
| `458` | WAREHOUSE, DISCOUNT STORE | impsegtype.csv |
| `4599` | IMPROVEMENT VALUE IN FIDALGO MARINA | impsegtype.csv |
| `460` | SHELL, NEIGH SHOP CTR | impsegtype.csv |
| `461` | SHELL, COMMUNITY SHOP CTR | impsegtype.csv |
| `462` | SHELL, REGIONAL SHOP CTR | impsegtype.csv |
| `466` | BOAT STORAGE SHED | impsegtype.csv |
| `467` | BOAT STORAGE BLDG | impsegtype.csv |
| `468` | MATERIAL STORAGE SHED | impsegtype.csv |
| `469` | FREESTALL BARN | impsegtype.csv |
| `470` | EQUIPMENT (SHOP) BLDG | impsegtype.csv |
| `471` | LIGHT COMMERCIAL UTILITY BLDG | impsegtype.csv |
| `472` | EQUIPMENT SHED | impsegtype.csv |
| `473` | MATERIAL SHELTER | impsegtype.csv |
| `474` | POULTRY HOUSE - CAGE OPERATION | impsegtype.csv |
| `475` | POULTRY HOUSE-FLOOR OPERATION | impsegtype.csv |
| `476` | FARM IMPLEMENT SHED | impsegtype.csv |
| `479` | FARM UTILITY STORAGE SHEDS | impsegtype.csv |
| `480` | VEGETABLE STORAGE | impsegtype.csv |
| `481` | MUSEUM | impsegtype.csv |
| `482` | CONVENTION CENTER | impsegtype.csv |
| `483` | FITNESS CENTER | impsegtype.csv |
| `484` | HIGH SCHOOL (ENTIRE) | impsegtype.csv |
| `485` | NATATORIUM (INDOOR SWIMMING POOL) | impsegtype.csv |
| `486` | FIELD HOUSE | impsegtype.csv |
| `487` | VOCATIONAL SCHOOL | impsegtype.csv |
| `488` | BOOK STORE (SCHOOL) | impsegtype.csv |
| `489` | JAIL-POLICE STATION | impsegtype.csv |
| `490` | KENNEL | impsegtype.csv |
| `491` | GOVERNMENT COMMUNITY SERVICE BLDG | impsegtype.csv |
| `493` | FLATHOUSE (GRAIN/RICE STORAGE) | impsegtype.csv |
| `494` | INDUSTRIAL LIGHT MFG | impsegtype.csv |
| `495` | INDUSTRIAL HEAVY MFG | impsegtype.csv |
| `496` | LABORATORIES | impsegtype.csv |
| `497` | COMPUTER CENTER | impsegtype.csv |
| `498` | BROADCAST FACILITIES | impsegtype.csv |
| `499` | DRY CLEANERS-LAUNDRY | impsegtype.csv |
| `5200` | FIDALGO MARINA | impsegtype.csv |
| `525` | MINI-WAREHOUSE, HI-RISE | impsegtype.csv |
| `526` | SERVICE GARAGE SHEDS | impsegtype.csv |
| `527` | MUNICIPAL SERVICE GARAGE | impsegtype.csv |
| `528` | SERVICE REPAIR GARAGE | impsegtype.csv |
| `529` | SNACK BAR | impsegtype.csv |
| `530` | CAFETERIA | impsegtype.csv |
| `531` | MINI-MART CONVENIENCE STORE | impsegtype.csv |
| `532` | FLORIST SHOP | impsegtype.csv |
| `533` | WAREHOUSE FOOD STORE | impsegtype.csv |
| `534` | WAREHOUSE SHOWROOM | impsegtype.csv |
| `539` | BED AND BREAKFAST INN | impsegtype.csv |
| `540` | MOTEL, 2 STORY DOUBLE ROW | impsegtype.csv |
| `541` | MOTEL, 2 STORY SINGLE ROW | impsegtype.csv |
| `542` | MOTEL, 1 STORY DOUBLE ROW | impsegtype.csv |
| `543` | MOTEL, 1 STORY SINGLE ROW | impsegtype.csv |
| `544` | OFFICE-APARTMENT (MOTEL) | impsegtype.csv |
| `551` | ROOMING HOUSE | impsegtype.csv |
| `552` | RECREATIONAL ENCLOSURE | impsegtype.csv |
| `554` | SHED OFFICE STRUCTURE | impsegtype.csv |
| `555` | LIGHT COMMERCIAL ARCH-RIB, QUONSET | impsegtype.csv |
| `556` | BULK OIL STORAGE | impsegtype.csv |
| `557` | FARM UTILITY ARCH RIB, QUONSET | impsegtype.csv |
| `558` | FARM IMPLEMENT ARCH-RIB, QUONSET | impsegtype.csv |
| `559` | STABLES, HIGH-VALUE | impsegtype.csv |
| `560` | LEAN-TO | impsegtype.csv |
| `561` | FEEDER BARN | impsegtype.csv |
| `562` | COMMODITY STORAGE SHED, FARM | impsegtype.csv |
| `563` | BAG FERTILIZER STORAGE | impsegtype.csv |
| `564` | DEHYDRATOR BLDG | impsegtype.csv |
| `565` | FARM UTILITY SHELTER | impsegtype.csv |
| `566` | FARM SUN SHADE SHELTER | impsegtype.csv |
| `567` | POULTRY HOUSE CAGE, TWO STORY | impsegtype.csv |
| `568` | POULTRY HOUSE CAGE ELEVATED TWO STORY | impsegtype.csv |
| `569` | POULTRY HOUSE CAGE THREE STORY | impsegtype.csv |
| `570` | POULTRY HOUSE-CAGE ELEVATED ONE STORY | impsegtype.csv |
| `571` | PASSENGER TERMINAL | impsegtype.csv |
| `573` | ARCADE BLDG | impsegtype.csv |
| `574` | VISITOR CENTER | impsegtype.csv |
| `575` | DINING ATRIUM | impsegtype.csv |
| `576` | ATRIUM | impsegtype.csv |
| `577` | PARKING LEVEL | impsegtype.csv |
| `578` | MINI-BANK | impsegtype.csv |
| `580` | TRUCK STOP | impsegtype.csv |
| `581` | POST OFFICE-MAIN | impsegtype.csv |
| `582` | POST OFFICE-BRANK OFFICE | impsegtype.csv |
| `583` | MAIL PROCESSING FACILITY | impsegtype.csv |
| `584` | MEGA WAREHOUSE | impsegtype.csv |
| `585` | MECHANICAL PENTHOUSE | impsegtype.csv |
| `586` | ROADSIDE MARKET | impsegtype.csv |
| `587` | SHELL, MULTIPLE RESIDENCE | impsegtype.csv |
| `588` | EXTENDED STAY MOTEL | impsegtype.csv |
| `589` | ELDERLY, ASSIT. MULTI RES | impsegtype.csv |
| `594` | HOTEL, FULL SERVICE | impsegtype.csv |
| `595` | HOTEL, LIMITED SERVICE | impsegtype.csv |
| `596` | SHELL, APARTMENT | impsegtype.csv |
| `599` | RELOCATABLE OFFICE | impsegtype.csv |
| `6L1` | COMMERCIAL LAND | impsegtype.csv |
| `6L3` | PUBLIC LAND | impsegtype.csv |
| `6M1` | CHURCH | impsegtype.csv |
| `6M11` | DAYCARE | impsegtype.csv |
| `6M12` | PRE-SCHOOL/PRIVATE SCHOOL | impsegtype.csv |
| `6M13` | UTILITY SUB-STATION | impsegtype.csv |
| `6M14` | MISCELLANEOUS | impsegtype.csv |
| `6M15` | SUBSIDIZED HOUSING | impsegtype.csv |
| `6M2` | MOBILE HOME PARK/RV PARK | impsegtype.csv |
| `6M3` | HOSPITAL | impsegtype.csv |
| `6M4` | NURSING HOME | impsegtype.csv |
| `6M5` | MOTEL/HOTEL | impsegtype.csv |
| `6M7` | PUBLIC BUILDING | impsegtype.csv |
| `6M9` | PUBLIC PARK | impsegtype.csv |
| `6MAPT` | APARTMENT | impsegtype.csv |
| `6O14` | LODGE/ASSEMBLY HALL | impsegtype.csv |
| `6O2` | GENERAL OFFICE | impsegtype.csv |
| `6O5` | MEDICAL/DENTAL OFFICE | impsegtype.csv |
| `6O7` | OFFICE CONDOMINIUM | impsegtype.csv |
| `6O9` | BANK | impsegtype.csv |
| `6R1` | GENERAL RETAIL | impsegtype.csv |
| `6R10` | RESTAURANT | impsegtype.csv |
| `6R11` | FAST FOOD RESTAURANT | impsegtype.csv |
| `6R12` | GREENHOUSE/NURSERY | impsegtype.csv |
| `6R13` | TAVERN | impsegtype.csv |
| `6R14` | STAND ALONE SUPERMARKET | impsegtype.csv |
| `6R22` | PARKING LOT | impsegtype.csv |
| `6R24` | THEATER | impsegtype.csv |
| `6R27` | BOWLING ALLEY | impsegtype.csv |
| `6R28` | GYM/HEALTH CLUB | impsegtype.csv |
| `6R32` | CEMETERY | impsegtype.csv |
| `6R33` | MORTUARY | impsegtype.csv |
| `6R34` | GOLF COURSE | impsegtype.csv |
| `6R38` | AIRPORT | impsegtype.csv |
| `6R39F` | CONVENIENCE STORE/FRANCHISE | impsegtype.csv |
| `6R39N` | CONVENIENCE STORE/NON-FRANCHISE | impsegtype.csv |
| `6R4` | NEIGHBORHOOD CENTER | impsegtype.csv |
| `6R46` | MARINA | impsegtype.csv |
| `6R5` | REGIONAL SHOPPING CENTER | impsegtype.csv |
| `6R6` | SERVICE STATION | impsegtype.csv |
| `6R7` | GARAGE/AUTO REPAIR | impsegtype.csv |
| `6R8` | CAR WASH | impsegtype.csv |
| `6R9` | AUTO SALES/SERVICE FACILITIES | impsegtype.csv |
| `728` | HORSE ARENA | impsegtype.csv |
| `7I19` | RADIO/TV TRANSMISSION FACILITY | impsegtype.csv |
| `7I2` | INDUSTRIAL BUILDING | impsegtype.csv |
| `7I21` | GRAVEL PIT | impsegtype.csv |
| `7I4` | SELF-STORAGE/MINI-STORAGE | impsegtype.csv |
| `7I6` | WAREHOUSE/DISTRIBUTION BUILDING | impsegtype.csv |
| `7L2` | MANUFACTURING LAND | impsegtype.csv |
| `987` | INTERIOR SPACE, MULTI RES | impsegtype.csv |
| `989` | INTERIOR SPACE, APARTMENT | impsegtype.csv |
| `990` | INTERIOR SPACE, NEIGH SHOP CTR | impsegtype.csv |
| `991` | INTERIOR SPACE, COMMUN SHOP CTR | impsegtype.csv |
| `992` | INTERIOR SPACE, REGIONAL SHOP CTR | impsegtype.csv |
| `993` | INTERIOR SPACE, OFFICE | impsegtype.csv |
| `994` | INTERIOR SPACE, INDUSTRIAL | impsegtype.csv |
| `ACPT` | ATTACHED CARPORT | impsegtype.csv |
| `AGAR` | ATTACHED GARAGE | impsegtype.csv |
| `ARNA` | ARENA | impsegtype.csv |
| `AS` | ASPHALT | impsegtype.csv |
| `ASPHALT` | ASPHALT PAVING | impsegtype.csv |
| `ATF` | FINISHED ATTIC | impsegtype.csv |
| `ATL` | ATTIC-LOW CST FIN | impsegtype.csv |
| `ATT` | LOFT/BONUS ROOM/ATTIC | impsegtype.csv |
| `ATU` | UNFIN ATTIC | impsegtype.csv |
| `BMF` | FINISHED BASEMENT | impsegtype.csv |
| `BML` | BASEMENT-LOW CST FIN | impsegtype.csv |
| `BMU` | UNFINISHED BASEMENT | impsegtype.csv |
| `BS` | BUNKER SILO | impsegtype.csv |
| `BSMT` | BASEMENT | impsegtype.csv |
| `BSWD` | BUNKER SILO WOOD SIDES | impsegtype.csv |
| `CARP` | CARPORT | impsegtype.csv |
| `CAVDOCK` | DOCKS - LK CAVANUAGH AREA | impsegtype.csv |
| `CBRET` | CONC/BLK RETAIN WALL | impsegtype.csv |
| `CCP` | Covered concrete porch | built-in |
| `CD` | CEDAR DECK/OUTDR WD | impsegtype.csv |
| `CFNC` | CHAIN LINK FENCE | impsegtype.csv |
| `CONC` | CONCRETE | impsegtype.csv |
| `CONCRETE` | CONCRETE | impsegtype.csv |
| `CP` | CONCRETE PORCH OR SLAB | impsegtype.csv |
| `CPA` | ATTACHED CARPORT | impsegtype.csv |
| `CPB` | BASEMENT CARPORT | impsegtype.csv |
| `CPD` | CARPORT-DET,GABLE/HIP ROOF | impsegtype.csv |
| `CPE` | BUILT IN CARPORT | impsegtype.csv |
| `CPF` | CARPORT DETACHED - FLAT ROOF | impsegtype.csv |
| `CPOR` | COVERED PORCH | impsegtype.csv |
| `CRET` | CONC. RETAINING WALL | impsegtype.csv |
| `CWP` | Covered wood porch | built-in |
| `DCPT` | DETACHED CARPORT | impsegtype.csv |
| `DECK` | WOOD DECK | impsegtype.csv |
| `DGAR` | DETACHED GARAGE | impsegtype.csv |
| `DOCK` | DOCK | impsegtype.csv |
| `DRAMP` | DOCK ACCESS RAMP | impsegtype.csv |
| `ENP` | ENCLOSED PORCH | impsegtype.csv |
| `FC` | FEED COVER | impsegtype.csv |
| `FD` | FIR DECK | impsegtype.csv |
| `FDB` | FEEDER BARN | impsegtype.csv |
| `FH` | FIRE HALL | impsegtype.csv |
| `FP` | FIREPLACE | impsegtype.csv |
| `FSB` | FREE STALL BARN | impsegtype.csv |
| `FSRET` | FIELD STONE RETAINING WALL | impsegtype.csv |
| `GA` | GARAGE-ATTACHED | impsegtype.csv |
| `GAF` | GARAGE, ATTACHED, FINISHED | impsegtype.csv |
| `GAL` | GAR ATT LOW CST FIN | impsegtype.csv |
| `GAR` | GARAGE | impsegtype.csv |
| `GAU` | GARAGE ATT UNFIN | impsegtype.csv |
| `GBI` | BSMT OR BUILT IN GARAGE | impsegtype.csv |
| `GDF` | FIN DET GAR | impsegtype.csv |
| `GDL` | DET.GAR.LOW CST FIN | impsegtype.csv |
| `GDU` | DET.UNFIN.GARAGE | impsegtype.csv |
| `GP` | TEST | impsegtype.csv |
| `GPB` | GENERAL PUR BLDG | impsegtype.csv |
| `GREENH` | GREEN HOUSE - RES | impsegtype.csv |
| `GRF` | FIN ATT GAR | impsegtype.csv |
| `GRL` | ATT GAR-LOW CST FN | impsegtype.csv |
| `GRNH` | GREENHOUSE | impsegtype.csv |
| `GRU` | UNFIN ATT GAR | impsegtype.csv |
| `HC` | HAY COVER | impsegtype.csv |
| `HSTB` | HOBBY STABLE | impsegtype.csv |
| `HT` | HOT TUB - SPA | impsegtype.csv |
| `IBDOCK` | INTERBAY CONDO'S DOCKS | impsegtype.csv |
| `IND` | INDUSTRIAL | impsegtype.csv |
| `LAG` | MANURE STORAGE LAGOON | impsegtype.csv |
| `LB` | LOFT BARN | impsegtype.csv |
| `LFT` | LOFT | impsegtype.csv |
| `LT` | LEAN TO | impsegtype.csv |
| `MA` | MAIN AREA | impsegtype.csv |
| `MB` | METAL BUILDING | impsegtype.csv |
| `MBHP` | MILK BARN HOLDING PEN | impsegtype.csv |
| `MCB` | METAL COMPONENT BLDG | impsegtype.csv |
| `MCBOFF` | METAL COMP BLDG OFFICE | impsegtype.csv |
| `MCBPART` | METAL COMP BLDG PARTITIONS | impsegtype.csv |
| `MHP` | MOBILE HOME PARK | impsegtype.csv |
| `MHS` | MOBILE PARK SITES | impsegtype.csv |
| `MLKB` | MILK BARN | impsegtype.csv |
| `MP` | MILK PARLOR | impsegtype.csv |
| `MPS` | MULTI-PURPOSE SHED | impsegtype.csv |
| `MSHD` | MACHINE SHED | impsegtype.csv |
| `OTB` | OUT BLDG | impsegtype.csv |
| `PBH` | POULTRY BROILER HOUSE | impsegtype.csv |
| `PLH` | POULTRY LAYING HOUSE | impsegtype.csv |
| `POR` | PORCH | impsegtype.csv |
| `PS` | POTATO STORAGE | impsegtype.csv |
| `QUAN` | QUANSET HUT | impsegtype.csv |
| `RAIL` | FENCE RAIL | impsegtype.csv |
| `RC` | ROOF COVER | impsegtype.csv |
| `REFINERY` | PETROLIUM REFINERY | impsegtype.csv |
| `RF` | ROOF COVER | impsegtype.csv |
| `SA` | SAUNA | impsegtype.csv |
| `SETUP` | MOBILE HOME SETUP VALUE | impsegtype.csv |
| `SHOP` | SHOP | impsegtype.csv |
| `SILO` | SILO | impsegtype.csv |
| `SP` | SWIMMING POOL | impsegtype.csv |
| `SU` | MOBILE HOME SETUP | impsegtype.csv |
| `SWMHP` | SEDRO WOOLLEY MOBILE HOME PARK | impsegtype.csv |
| `TC` | TENNIS COURT | impsegtype.csv |
| `TO` | TIP OUT | impsegtype.csv |
| `UF2` | 2nd FLOOR LIVING AREA | impsegtype.csv |
| `UF3` | 3rd FLOOR LIVING AREA | impsegtype.csv |
| `UTB` | UTILITY BUILDING | impsegtype.csv |
| `UTIL` | SEPTIC,POWER,WATER | impsegtype.csv |
| `WD` | WOOD DECK | impsegtype.csv |
| `WP` | WOOD PORCH | impsegtype.csv |

## `neighborhood` Mappings
| Code | Description | Source |
| --- | --- | --- |
| `000` | UNIQUE PROPERTIES | neighborhood.csv |
| `100` | SPECIAL PLATS; NO IMPROVEMENTS | neighborhood.csv |
| `101` | SPECIAL PLATS; OTHER IMPROVEMENTS | neighborhood.csv |
| `102` | SPECIAL PLATS; RES | neighborhood.csv |
| `103` | SPECIAL PLATS; 2+ RES | neighborhood.csv |
| `104` | SPECIAL PLATS; MOBILE/MANF. HOME | neighborhood.csv |
| `105` | SPECIAL PLATS; PARK MODEL MOBILE | neighborhood.csv |
| `106` | SPECIAL PLATS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `107` | SPECIAL PLATS; P.U.D | neighborhood.csv |
| `108` | SPECIAL PLATS; CONDO | neighborhood.csv |
| `109` | SPECIAL PLATS; IMPROVEMENT + EXCESS LAND | neighborhood.csv |
| `110` | PLATTED LOTS; NO IMPROVEMENTS | neighborhood.csv |
| `111` | PLATTED LOTS; OTHER IMPROVEMENTS | neighborhood.csv |
| `112` | PLATTED LOTS; RES | neighborhood.csv |
| `113` | PLATTED LOTS; 2+ RES | neighborhood.csv |
| `114` | PLATTED LOTS; MOBILE/MANF. HOME | neighborhood.csv |
| `115` | PLATTED LOTS; PARK MODEL MOBILE | neighborhood.csv |
| `116` | PLATTED LOTS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `117` | PLATTED LOTS; P.U.D. | neighborhood.csv |
| `118` | PLATTED LOTS; CONDO | neighborhood.csv |
| `119` | PLATTED LOTS; IMPROVEMENT + EXCESS LAND | neighborhood.csv |
| `120` | S.F. UNPLATTED UP TO .5 AC; NO IMPROVEMENTS | neighborhood.csv |
| `121` | S.F. UNPLATTED UP TO .5 AC; OTHER IMPROVEMENTS | neighborhood.csv |
| `122` | S.F. UNPLATTED UP TO .5 AC; RES | neighborhood.csv |
| `123` | S.F. UNPLATTED UP TO .5 AC; 2+ RES | neighborhood.csv |
| `124` | S.F. UNPLATTED UP TO .5 AC; MOBILE/MANF. HOME | neighborhood.csv |
| `125` | S.F. UNPLATTED UP TO .5 AC; PARK MODEL MOBILE | neighborhood.csv |
| `126` | S.F. UNPLATTED UP TO .5 AC; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `127` | S.F. UNPLATTED UP TO .5 AC; P.U.D. | neighborhood.csv |
| `128` | S.F. UNPLATTED UP TO .5 AC; CONDO | neighborhood.csv |
| `130` | S.F. UNPLATTED .51 TO 1 AC; NO IMPROVEMENTS | neighborhood.csv |
| `131` | S.F. UNPLATTED .51 TO 1 AC; OTHER IMPROVEMENTS | neighborhood.csv |
| `132` | S.F. UNPLATTED .51 TO 1 AC; RES | neighborhood.csv |
| `133` | S.F. UNPLATTED .51 TO 1 AC; 2+ RES | neighborhood.csv |
| `134` | S.F. UNPLATTED .51 TO 1 AC; MOBILE/MANF. HOME | neighborhood.csv |
| `135` | S.F. UNPLATTED .51 TO 1 AC; PARK MODEL MOBILE | neighborhood.csv |
| `136` | S.F. UNPLATTED .51 TO 1 AC; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `137` | S.F. UNPLATTED .51 TO 1 AC; P.U.D. | neighborhood.csv |
| `138` | S.F. UNPLATTED .51 TO 1 AC; CONDO | neighborhood.csv |
| `150` | PLATTED CAMPING TRACTS; NO IMPROVEMENTS | neighborhood.csv |
| `151` | PLATTED CAMPING TRACTS; OTHER IMPROVEMENTS | neighborhood.csv |
| `152` | PLATTED CAMPING TRACTS; RES | neighborhood.csv |
| `153` | PLATTED CAMPING TRACTS; 2+ RES | neighborhood.csv |
| `154` | PLATTED CAMPING TRACTS; MOBILE/MANF HOME | neighborhood.csv |
| `155` | PLATTED CAMPING TRACTS; PARK MODEL MOBILE | neighborhood.csv |
| `156` | PLATTED CAMPING TRACTS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `160` | COMMUNITY PROPERTY; NO IMPROVEMENTS | neighborhood.csv |
| `161` | COMMUNITY PROPERTY; OTHER IMPROVEMENTS | neighborhood.csv |
| `162` | COMMUNITY PROPERTY; RES | neighborhood.csv |
| `163` | COMMUNITY PROPERTY; 2+ RES | neighborhood.csv |
| `164` | COMMUNITY PROPERTY; MOBILE/MANF. HOME | neighborhood.csv |
| `165` | COMMUNITY PROPERTY; PARK MODEL MOBILE | neighborhood.csv |
| `166` | COMMUNITY PROPERTY; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `167` | COMMUNITY PROPERTY; P.U.D. | neighborhood.csv |
| `168` | COMMUNITY PROPERTY; CONDO | neighborhood.csv |
| `170` | IMPROVEMENT ON LEASED LAND; NO IMPROVEMENTS | neighborhood.csv |
| `171` | IMPROVEMENT ON LEASED LAND; OTHER IMPROVEMENTS | neighborhood.csv |
| `172` | IMPROVEMENT ON LEASED LAND; RES | neighborhood.csv |
| `173` | IMPROVEMENT ON LEASED LAND; 2+ RES | neighborhood.csv |
| `174` | IMPROVEMENT ON LEASED LAND; MOBILE/MANF. HOME | neighborhood.csv |
| `175` | IMPROVEMENT ON LEASED LAND; PARK MODEL MOBILE | neighborhood.csv |
| `176` | IMPROVEMENT ON LEASED LAND; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `177` | IMPROVEMENT ON LEASED LAND; P.U.D. | neighborhood.csv |
| `178` | IMPROVEMENT ON LEASED LAND; CONDO | neighborhood.csv |
| `180` | DUPLEX & TRIPLEX; NO IMPROVEMENTS | neighborhood.csv |
| `186` | DUPLEX & TRIPLEX; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `186D` | DUPLEX - BUILT AS | neighborhood.csv |
| `186F` | FOURPLEX - BUILT AS | neighborhood.csv |
| `186T` | TRIPLEX - BUILT AS | neighborhood.csv |
| `190` | OLD HOME DU-/TRIPLEX; NO IMPROVEMENTS | neighborhood.csv |
| `191` | OLD HOME DU-/TRIPLEX; OTHER IMPROVEMENTS | neighborhood.csv |
| `196` | OLD HOME DU-/TRIPLEX; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `196D` | DUPLEX - OLD HOME CONVERSION | neighborhood.csv |
| `196F` | FOURPLEX - OLD HOME CONVERSION | neighborhood.csv |
| `196T` | TRIPLEX - OLD HOME CONVERSION | neighborhood.csv |
| `1RW` | RESIDENTIAL RIGHT OF WAY | neighborhood.csv |
| `200` | NO/LOW BANK <15'; NO IMPROVEMENTS | neighborhood.csv |
| `201` | NO/LOW BANK <15'; OTHER IMPROVEMENTS | neighborhood.csv |
| `202` | NO/LOW BANK <15'; RES | neighborhood.csv |
| `203` | NO/LOW BANK <15'; 2+ RES | neighborhood.csv |
| `204` | NO/LOW BANK <15'; MOBILE/MANF. HOME | neighborhood.csv |
| `205` | NO/LOW BANK <15'; PARK MODEL MOBILE | neighborhood.csv |
| `206` | NO/LOW BANK <15'; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `207` | NO/LOW BANK <15'; P.U.D. | neighborhood.csv |
| `208` | NO/LOW BANK <15'; CONDO | neighborhood.csv |
| `210` | MED BANK 16-50'; NO IMPROVEMENTS | neighborhood.csv |
| `211` | MED BANK 16-50'; OTHER IMPROVEMENTS | neighborhood.csv |
| `212` | MED BANK 16-50'; RES | neighborhood.csv |
| `213` | MED BANK 16-50'; 2+ RES | neighborhood.csv |
| `214` | MED BANK 16-50'; MOBILE/MANF. HOME | neighborhood.csv |
| `215` | MED BANK 16-50'; PARK MODEL MOBILE | neighborhood.csv |
| `216` | MED BANK 16-50'; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `217` | MED BANK 16-50'; P.U.D. | neighborhood.csv |
| `218` | MED BANK 16-50'; CONDO | neighborhood.csv |
| `220` | HIGH BANK >50'; NO IMPROVEMENTS | neighborhood.csv |
| `221` | HIGH BANK >50'; OTHER IMPROVEMENTS | neighborhood.csv |
| `222` | HIGH BANK >50'; RES | neighborhood.csv |
| `223` | HIGH BANK >50'; 2+ RES | neighborhood.csv |
| `224` | HIGH BANK >50'; MOBILE/MANF. HOME | neighborhood.csv |
| `225` | HIGH BANK >50'; PARK MODEL MOBILE | neighborhood.csv |
| `226` | HIGH BANK >50'; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `227` | HIGH BANK >50'; P.U.D. | neighborhood.csv |
| `228` | HIGH BANK >50'; CONDO | neighborhood.csv |
| `23` | WATERFRONT | neighborhood.csv |
| `230` | ACREAGE; NO IMPROVEMENTS | neighborhood.csv |
| `231` | ACREAGE; OTHER IMPROVEMENTS | neighborhood.csv |
| `232` | ACREAGE; RES | neighborhood.csv |
| `233` | ACREAGE; 2+ RES | neighborhood.csv |
| `234` | ACREAGE; MOBILE/MANF. HOME | neighborhood.csv |
| `235` | WATERFONT ACREAGE; PARK MODEL MOBILE | neighborhood.csv |
| `236` | ACREAGE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `237` | ACREAGE; P.U.D. | neighborhood.csv |
| `238` | ACREAGE; CONDO | neighborhood.csv |
| `240` | AVERAGE VIEW - MARINE; NO IMPROVEMENTS | neighborhood.csv |
| `241` | AVERAGE VIEW - MARINE; OTHER IMPROVEMENTS | neighborhood.csv |
| `242` | AVERAGE VIEW - MARINE; RES | neighborhood.csv |
| `243` | AVERAGE VIEW - MARINE; 2+ RES | neighborhood.csv |
| `244` | AVERAGE VIEW - MARINE; MOBILE/MANF. HOME | neighborhood.csv |
| `245` | AVERAGE VIEW - MARINE; PARK MODEL MOBILE | neighborhood.csv |
| `246` | AVERAGE VIEW - MARINE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `247` | AVERAGE VIEW - MARINE; P.U.D. | neighborhood.csv |
| `248` | AVERAGE VIEW - MARINE; CONDO | neighborhood.csv |
| `250` | GOOD VIEW - MARINE; NO IMPROVEMENTS | neighborhood.csv |
| `251` | GOOD VIEW - MARINE; OTHER IMPROVEMENTS | neighborhood.csv |
| `252` | GOOD VIEW - MARINE; RES | neighborhood.csv |
| `253` | GOOD VIEW - MARINE; 2+ RES | neighborhood.csv |
| `254` | GOOD VIEW - MARINE; MOBILE/MANF. HOME | neighborhood.csv |
| `255` | GOOD VIEW - MARINE; PARK MODEL MOBILE | neighborhood.csv |
| `256` | GOOD VIEW - MARINE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `257` | GOOD VIEW - MARINE; P.U.D. | neighborhood.csv |
| `258` | GOOD VIEW - MARINE; CONDO | neighborhood.csv |
| `260` | PRIME VIEW - MARINE; NO IMPROVEMENTS | neighborhood.csv |
| `261` | PRIME VIEW - MARINE; OTHER IMPROVEMENTS | neighborhood.csv |
| `262` | PRIME VIEW - MARINE; RES | neighborhood.csv |
| `263` | PRIME VIEW - MARINE; 2+ RES | neighborhood.csv |
| `264` | PRIME VIEW - MARINE; MOBILE/MANF. HOME | neighborhood.csv |
| `265` | PRIME VIEW - MARINE; PARK MODEL MOBILE | neighborhood.csv |
| `266` | PRIME VIEW - MARINE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `267` | PRIME VIEW - MARINE; P.U.D. | neighborhood.csv |
| `268` | PRIME VIEW - MARINE; CONDO | neighborhood.csv |
| `270` | AVERAGE VIEW - TERRITORIAL; NO IMPROVEMENTS | neighborhood.csv |
| `271` | AVERAGE VIEW - TERRITORIAL; OTHER IMPROVEMENTS | neighborhood.csv |
| `272` | AVERAGE VIEW - TERRITORIAL; RES | neighborhood.csv |
| `273` | AVERAGE VIEW - TERRITORIAL; 2+ RES | neighborhood.csv |
| `274` | AVERAGE VIEW - TERRITORIAL; MOBILE/MANF. HOME | neighborhood.csv |
| `275` | AVERAGE VIEW - TERRITORIAL; PARK MODEL MOBILE | neighborhood.csv |
| `276` | AVERAGE VIEW - TERRITORIAL; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `277` | AVERAGE VIEW - TERRITORIAL; P.U.D. | neighborhood.csv |
| `278` | AVERAGE VIEW - TERRITORIAL; CONDO | neighborhood.csv |
| `280` | GOOD VIEW - TERRITORIAL; NO IMPROVEMENTS | neighborhood.csv |
| `281` | GOOD VIEW - TERRITORIAL; OTHER IMPROVEMENTS | neighborhood.csv |
| `282` | GOOD VIEW - TERRITORIAL; RES | neighborhood.csv |
| `283` | GOOD VIEW - TERRITORIAL; 2+ RES | neighborhood.csv |
| `284` | GOOD VIEW - TERRITORIAL; MOBILE/MANF. HOME | neighborhood.csv |
| `285` | GOOD VIEW - TERRITORIAL; PARK MODEL MOBILE | neighborhood.csv |
| `286` | GOOD VIEW - TERRITORIAL; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `287` | GOOD VIEW - TERRITORIAL;P P.U.D. | neighborhood.csv |
| `288` | GOOD VIEW - TERRITORIAL; CONDO | neighborhood.csv |
| `290` | PRIME VIEW - TERRITORIAL; NO IMPROVEMENTS | neighborhood.csv |
| `291` | PRIME VIEW - TERRITORIAL; OTHER IMPROVEMENTS | neighborhood.csv |
| `292` | PRIME VIEW - TERRITORIAL; RES | neighborhood.csv |
| `293` | PRIME VIEW - TERRITORIAL; 2+ RES | neighborhood.csv |
| `294` | PRIME VIEW - TERRITORIAL; MOBILE/MANF. HOME | neighborhood.csv |
| `295` | PRIME VIEW - TERRITORIAL; PARK MODEL MOBILE | neighborhood.csv |
| `296` | PRIME VIEW - TERRITORIAL; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `297` | PRIME VIEW - TERRITORIAL; P.U.D. | neighborhood.csv |
| `298` | PRIME VIEW - TERRITORIAL; CONDO | neighborhood.csv |
| `3` | ACREAGE | neighborhood.csv |
| `310` | 1.01-2.49 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `311` | 1.01-2.49 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `312` | 1.01-2.49 ACRES; RES | neighborhood.csv |
| `313` | 1.01-2.49 ACRES; 2+ RES | neighborhood.csv |
| `314` | 1.01-2.49 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `315` | 1.01-2.49 ACRES;PARK MODEL | neighborhood.csv |
| `316` | 1.01-2.49 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `320` | 2.5-4.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `321` | 2.5-4.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `322` | 2.5-4.99 ACRES; RES | neighborhood.csv |
| `323` | 2.5-4.99 ACRES; 2+ RES | neighborhood.csv |
| `324` | 2.5-4.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `326` | 2.5-4.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `330` | 5-9.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `331` | 5-9.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `332` | 5-9.99 ACRES; RES | neighborhood.csv |
| `333` | 5-9.99 ACRES; 2+ RES | neighborhood.csv |
| `334` | 5-9.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `336` | 5-9.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `340` | 10-19.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `341` | 10-19.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `342` | 10-19.99 ACRES; RES | neighborhood.csv |
| `343` | 10-19.99 ACRES; 2+ RES | neighborhood.csv |
| `344` | 10-19.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `346` | 10-19.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `350` | 20-39.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `351` | 20-39.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `352` | 20-39.99 ACRES; RES | neighborhood.csv |
| `353` | 20-39.99 ACRES; 2+ RES | neighborhood.csv |
| `354` | 20-39.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `356` | 20-39.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `360` | 40-79.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `361` | 40-79.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `362` | 40-79.99 ACRES; RES | neighborhood.csv |
| `363` | 40-79.99 ACRES; 2+ RES | neighborhood.csv |
| `364` | 40-79.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `366` | 40-79.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `370` | 80+ ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `371` | 80+ ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `372` | 80+ ACRES; RES | neighborhood.csv |
| `373` | 80+ ACRES; 2+ RES | neighborhood.csv |
| `374` | 80+ ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `376` | 80+ ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `4` | WETLANDS | neighborhood.csv |
| `410` | TIDELANDS; NO IMPROVEMENTS | neighborhood.csv |
| `420` | OYSTER LANDS; NO IMPROVEMENTS | neighborhood.csv |
| `421` | OYSTER LANDS; OTHER IMPROVEMENTS | neighborhood.csv |
| `426` | OYSTER LANDS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `430` | MARSH LANDS; NO IMPROVEMENTS | neighborhood.csv |
| `450` | FLOOD PLAIN; NO IMPROVEMENTS | neighborhood.csv |
| `451` | FLOOD PLAIN; OTHER IMPROVEMENTS | neighborhood.csv |
| `452` | FLOOD PLAIN; RES | neighborhood.csv |
| `453` | FLOOD PLAIN; 2+ RES | neighborhood.csv |
| `454` | FLOOD PLAIN; MOBILE/MANF. HOME | neighborhood.csv |
| `456` | FLOOD PLAIN; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `460` | FLOODWAY; NO IMPROVEMENTS | neighborhood.csv |
| `461` | FLOODWAY; OTHER IMPROVEMENTS | neighborhood.csv |
| `462` | FLOODWAY; RES | neighborhood.csv |
| `463` | FLOODWAY; 2+ RES | neighborhood.csv |
| `464` | FLOODWAY; MOBILE/MANF. HOME | neighborhood.csv |
| `465` | FLOODWAY; PARK MODEL MOBILE | neighborhood.csv |
| `466` | FLOODWAY; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `481` | CONDO MOORAGE - SKYLINE | neighborhood.csv |
| `482` | CONDO MOORAGE - ANCHOR COVE MARINA | neighborhood.csv |
| `483` | CONDO MOORAGE - ANACORTES MARINA | neighborhood.csv |
| `484` | CONDO MOORAGE - FIDALGO MARINA | neighborhood.csv |
| `510` | 4-10 UNITS; NO IMPROVEMENTS | neighborhood.csv |
| `511` | 4-10 UNITS; OTHER IMPROVEMENTS | neighborhood.csv |
| `516` | 4-10 UNITS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `520` | 11-20 UNITS; NO IMPROVEMENTS | neighborhood.csv |
| `521` | 11-20 UNITS; OTHER IMPROVEMENTS | neighborhood.csv |
| `526` | 11-20 UNITS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `530` | 21+ UNITS; NO IMPROVEMENTS | neighborhood.csv |
| `531` | 21+ UNITS; OTHER IMPROVEMENTS | neighborhood.csv |
| `536` | 21+ UNITS; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `570` | MOBILE HOME PARK; NO IMPROVEMENTS | neighborhood.csv |
| `571` | MOBILE HOME PARK; OTHER IMPROVEMENTS | neighborhood.csv |
| `576` | MOBILE HOME PARK | neighborhood.csv |
| `586` | BED & BREAKFAST | neighborhood.csv |
| `6` | COMMERCIAL | neighborhood.csv |
| `600` | COMMERCIAL - SPECIAL; NO IMPROVEMENTS | neighborhood.csv |
| `601` | COMMERCIAL - SPECIAL; OTHER IMPROVEMENTS | neighborhood.csv |
| `602` | COMMERCIAL - SPECIAL; RES | neighborhood.csv |
| `603` | COMMERCIAL - SPECIAL; 2+ RES | neighborhood.csv |
| `604` | COMMERCIAL - SPECIAL; MOBILE/MANF. HOME | neighborhood.csv |
| `605` | MEDICAL/DENTAL BLDG | neighborhood.csv |
| `606` | COMMERCIAL - SPECIAL; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `610` | COMMERCIAL - STRIP; NO IMPROVEMENTS | neighborhood.csv |
| `611` | COMMERCIAL - STRIP; OTHER IMPROVEMENTS | neighborhood.csv |
| `612` | COMMERCIAL - STRIP; RES | neighborhood.csv |
| `613` | COMMERCIAL - STRIP; 2+ RES | neighborhood.csv |
| `614` | COMMERCIAL - STRIP; MOBILE/MANF. HOME | neighborhood.csv |
| `616` | COMMERCIAL - STRIP; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `620` | COMMERCIAL - COMPLEX; NO IMPROVEMENTS | neighborhood.csv |
| `621` | COMMERCIAL - COMPLEX; OTHER IMPROVEMENTS | neighborhood.csv |
| `622` | COMMERCIAL - COMPLEX; RES | neighborhood.csv |
| `623` | COMMERCIAL - COMPLEX; 2+ RES | neighborhood.csv |
| `624` | COMMERCIAL - COMPLEX; MOBILE/MANF. HOME | neighborhood.csv |
| `626` | COMMERCIAL - COMPLEX; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `628` | COMMERCIAL - COMPLEX - CONDO | neighborhood.csv |
| `640` | COMMERCIAL - SITE; NO IMPROVEMENTS | neighborhood.csv |
| `641` | COMMERCIAL - SITE; OTHER IMPROVEMENTS | neighborhood.csv |
| `642` | COMMERCIAL - SITE; RES | neighborhood.csv |
| `643` | COMMERCIAL - SITE; 2+ RES | neighborhood.csv |
| `644` | COMMERCIAL - SITE; MOBILE/MANF. HOME | neighborhood.csv |
| `646` | COMMERCIAL - SITE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `660` | OFFICE - SITE; NO IMPROVEMENTS | neighborhood.csv |
| `661` | OFFICE - SITE; OTHER IMPROVEMENTS | neighborhood.csv |
| `662` | OFFICE - SITE; RES | neighborhood.csv |
| `663` | OFFICE - SITE; 2+ RES | neighborhood.csv |
| `664` | OFFICE - SITE; MOBILE/MANF. HOME | neighborhood.csv |
| `666` | OFFICE - SITE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `670` | OFFICE - COMPLEX; NO IMPROVEMENTS | neighborhood.csv |
| `671` | OFFICE - COMPLEX; OTHER IMPROVEMENTS | neighborhood.csv |
| `672` | OFFICE - COMPLEX; RES | neighborhood.csv |
| `673` | OFFICE - COMPLEX; 2+ RES | neighborhood.csv |
| `674` | OFFICE - COMPLEX; MOBILE/MANF. HOME | neighborhood.csv |
| `676` | OFFICE - COMPLEX; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `680` | MISC.; NO IMPROVEMENTS | neighborhood.csv |
| `681` | MISC.; OTHER IMPROVEMENTS | neighborhood.csv |
| `682` | MISC.; RES | neighborhood.csv |
| `683` | MISC.; 2+ RES | neighborhood.csv |
| `684` | MISC.; MOBILE/MANF. HOME | neighborhood.csv |
| `686` | MISC.; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `696` | IMPROVEMENT ON LEASED LAND | neighborhood.csv |
| `6L1` | COMMERCIAL LAND | neighborhood.csv |
| `6L3` | PUBLIC LAND | neighborhood.csv |
| `6M1` | CHURCH | neighborhood.csv |
| `6M11` | DAYCARE | neighborhood.csv |
| `6M12` | PRESCHOOL/PRIVATE SCHOOL | neighborhood.csv |
| `6M13` | UTILITY SUB-STATION | neighborhood.csv |
| `6M14` | MISCELLANEOUS | neighborhood.csv |
| `6M15` | SUBSIDIZED HOUSING | neighborhood.csv |
| `6M2` | MOBILE HOME/ RV PARK | neighborhood.csv |
| `6M3` | HOSPITAL | neighborhood.csv |
| `6M4` | NURSING HOME/RETIREMENT HOME | neighborhood.csv |
| `6M5` | HOTEL/MOTEL | neighborhood.csv |
| `6M7` | PUBLIC BLDG | neighborhood.csv |
| `6M9` | PUBLIC PARK | neighborhood.csv |
| `6MAPT` | APARTMENT | neighborhood.csv |
| `6O14` | LODGE/ASSEMBLY HALL | neighborhood.csv |
| `6O2` | GENERAL OFFICE | neighborhood.csv |
| `6O5` | MEDICAL/DENTAL BLDG | neighborhood.csv |
| `6O7` | OFFICE CONDOMINIUM | neighborhood.csv |
| `6O9` | BANK | neighborhood.csv |
| `6R1` | GENERAL RETAIL | neighborhood.csv |
| `6R10` | RESTAURANT | neighborhood.csv |
| `6R11` | FAST FOOD RESTAURANT | neighborhood.csv |
| `6R12` | GREENHOUSE/NURSERY | neighborhood.csv |
| `6R13` | TAVERN | neighborhood.csv |
| `6R14` | STAND ALONE SUPERMARKET | neighborhood.csv |
| `6R22` | PARKING LOT | neighborhood.csv |
| `6R23` | MORTUARY | neighborhood.csv |
| `6R24` | THEATER | neighborhood.csv |
| `6R27` | BOWLING ALLEY | neighborhood.csv |
| `6R28` | GYM/HEALTH CLUB | neighborhood.csv |
| `6R32` | CEMETERY | neighborhood.csv |
| `6R33` | MORTUARY | neighborhood.csv |
| `6R34` | GOLF COURSE | neighborhood.csv |
| `6R38` | AIRPORT | neighborhood.csv |
| `6R39F` | CONVENIENCE STORE-FRANCHISE | neighborhood.csv |
| `6R39N` | CONVENIENCE STORE-NON-FRANCHISE | neighborhood.csv |
| `6R4` | NEIGHBORHOOD CENTER | neighborhood.csv |
| `6R46` | MARINA | neighborhood.csv |
| `6R47` | SERVICE STATION/MINI-MART | neighborhood.csv |
| `6R5` | REGIONAL SHOPPING CENTER | neighborhood.csv |
| `6R6` | SERVICE STATION | neighborhood.csv |
| `6R7` | GARAGE/AUTO REPAIR | neighborhood.csv |
| `6R8` | CAR WASH | neighborhood.csv |
| `6R9` | AUTO SALES/SERVICE FACILITIES | neighborhood.csv |
| `6RW` | COMMERCIAL RIGHT OF WAY | neighborhood.csv |
| `700` | "TCO 's" | neighborhood.csv |
| `710` | MFG. - SITE; NO IMPROVEMENTS | neighborhood.csv |
| `711` | MFG. - SITE; OTHER IMPROVEMENTS | neighborhood.csv |
| `712` | MFG. - SITE; RES | neighborhood.csv |
| `713` | MFG. - SITE; 2+ RES | neighborhood.csv |
| `714` | MFG. - SITE; MOBILE/MANF. HOME | neighborhood.csv |
| `716` | MFG. - SITE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `720` | MFG. - ACREAGES; NO IMPROVEMENTS | neighborhood.csv |
| `721` | MFG. - ACREAGES; OTHER IMPROVEMENTS | neighborhood.csv |
| `722` | MFG. - ACREAGES; RES | neighborhood.csv |
| `723` | MFG. - ACREAGES; 2+ RES | neighborhood.csv |
| `724` | MFG. - ACREAGES; MOBILE/MANF. HOME | neighborhood.csv |
| `726` | MFG. - ACREAGES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `730` | ZONED INDUSTRIAL - RESIDENTIAL USE | neighborhood.csv |
| `731` | ZONED INDUSTRIAL - RESIDENTIAL USE / MISC. IMP. | neighborhood.csv |
| `732` | ZONED INDUSTRIAL - RESIDENTIAL USE / SFR | neighborhood.csv |
| `734` | ZONED INDUSTRIAL - RESIDENTIAL USE / MANUF. HOME | neighborhood.csv |
| `750` | STORAGE - SITE; NO IMPROVEMENTS | neighborhood.csv |
| `751` | STORAGE - SITE; OTHER IMPROVEMENTS | neighborhood.csv |
| `752` | STORAGE - SITE; RES | neighborhood.csv |
| `753` | STORAGE - SITE; 2+ RES | neighborhood.csv |
| `754` | STORAGE - SITE; MOBILE/MANF. HOME | neighborhood.csv |
| `756` | STORAGE - SITE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `760` | STORAGE - ACREAGE; NO IMPROVEMENTS | neighborhood.csv |
| `761` | STORAGE - ACREAGE; OTHER IMPROVEMENTS | neighborhood.csv |
| `762` | STORAGE - ACREAGE; RES | neighborhood.csv |
| `763` | STORAGE - ACREAGE; 2+ RES | neighborhood.csv |
| `764` | STORAGE - ACREAGE; MOBILE/MANF. HOME | neighborhood.csv |
| `766` | STORAGE - ACREAGE; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `770` | GRAVEL PITS | neighborhood.csv |
| `771` | GRAVEL PIT WITH MISC BLDG | neighborhood.csv |
| `776` | GRAVEL PIT WITH COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `7I19` | RADIO/TV TRANSMISSION FACILITY | neighborhood.csv |
| `7I2` | INDUSTRIAL BLDG | neighborhood.csv |
| `7I21` | GRAVEL PITS | neighborhood.csv |
| `7I4` | SELF STORAGE/MINI-STORAGE | neighborhood.csv |
| `7I6` | WAREHOUSE | neighborhood.csv |
| `7L2` | INDUSTRIAL LAND | neighborhood.csv |
| `800` | 1.01 - 2.49 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `801` | 1.01 - 2.49 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `802` | 1.01 - 2.49 ACRES; RES | neighborhood.csv |
| `803` | 1.01 - 2.49 ACRES; 2+ RES | neighborhood.csv |
| `804` | 1.01 - 2.49 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `806` | 1.01 - 2.49 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `80D` | 1.01-2.49 ACRES; DAIRY | neighborhood.csv |
| `80NOD` | 1.01-2.49 ACRES; NON OPERATING DAIRY | neighborhood.csv |
| `810` | 2.5 - 4.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `811` | 2.5 - 4.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `812` | 2.5 - 4.99 ACRES; RES | neighborhood.csv |
| `813` | 2.5 - 4.99 ACRES; 2+ RES | neighborhood.csv |
| `814` | 2.5 - 4.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `816` | 2.5 - 4.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `81D` | 2.5-4.9 ACRES; DAIRY | neighborhood.csv |
| `81NOD` | 2.5-4.9 ACRES; NON OPERATING DAIRY | neighborhood.csv |
| `820` | 5 - 9.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `821` | 5 - 9.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `822` | 5 - 9.99 ACRES; RES | neighborhood.csv |
| `823` | 5 - 9.99 ACRES; 2+ RES | neighborhood.csv |
| `824` | 5 - 9.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `826` | 5 - 9.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `82D` | 2.5-4.99; DAIRY | neighborhood.csv |
| `82NOD` | 2.5-4.99; NON OPERATING DAIRY | neighborhood.csv |
| `830` | 10 - 19.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `831` | 10 - 19.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `832` | 10 - 19.99 ACRES; RES | neighborhood.csv |
| `833` | 10 - 19.99 ACRES; 2+ RES | neighborhood.csv |
| `834` | 10 - 19.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `836` | 10 - 19.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `83D` | 10-19.99 ACRES; DAIRY | neighborhood.csv |
| `83NOD` | 10-19.99 ACRES; NON OPERATING DAIRY | neighborhood.csv |
| `840` | 20 - 39.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `841` | 20 - 39.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `842` | 20 - 39.99 ACRES; RES | neighborhood.csv |
| `843` | 20 - 39.99 ACRES; 2+ RES | neighborhood.csv |
| `844` | 20 - 39.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `846` | 20 - 39.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `84D` | 20-39.99 ACRES; DAIRY | neighborhood.csv |
| `84NOD` | 20-39.99 ACRES; NON OPERATING DAIRY | neighborhood.csv |
| `850` | 40 - 79.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `851` | 40 - 79.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `852` | 40 - 79.99 ACRES; RES | neighborhood.csv |
| `853` | 40 - 79.99 ACRES; 2+ RES | neighborhood.csv |
| `854` | 40 - 79.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `856` | 40 - 79.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `85D` | 40-79.99 ACRES; DAIRY | neighborhood.csv |
| `85NOD` | 40-79.99 ACRES; NON OPERATING DAIRY | neighborhood.csv |
| `860` | 80+ ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `861` | 80+ ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `862` | 80+ ACRES; RES | neighborhood.csv |
| `863` | 80+ ACRES; 2+ RES | neighborhood.csv |
| `864` | 80+ ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `866` | 80+ ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `86D` | 80+ ACRES; DAIRY | neighborhood.csv |
| `86NOD` | 80+ ACRES; NON OPERATING DAIRY | neighborhood.csv |
| `870` | 0 - 9.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `871` | 0 - 9.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `872` | 0 - 9.99 ACRES; RES | neighborhood.csv |
| `873` | 0 - 9.99 ACRES; 2+ RES | neighborhood.csv |
| `874` | 0 - 9.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `876` | 0 - 9.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `880` | 10 - 19.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `881` | 10 - 19.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `882` | 10 - 19.99 ACRES; RES | neighborhood.csv |
| `883` | 10 - 19.99 ACRES; 2+ RES | neighborhood.csv |
| `884` | 10 - 19.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `886` | 10 - 19.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `890` | 20+ ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `891` | 20+ ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `892` | 20+ ACRES; RES | neighborhood.csv |
| `893` | 20+ ACRES; 2+ RES | neighborhood.csv |
| `894` | 20+ ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `896` | 20+ ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `900` | 0 - 4.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `901` | 0 - 4.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `902` | 0 - 4.99 ACRES; RES | neighborhood.csv |
| `903` | 0 - 4.99 ACRES; 2+ RES | neighborhood.csv |
| `904` | 0 - 4.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `906` | 0 - 4.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `910` | 5 - 9.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `911` | 5 - 9.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `912` | 5 - 9.99 ACRES; RES | neighborhood.csv |
| `913` | 5 - 9.99 ACRES; 2+ RES | neighborhood.csv |
| `914` | 5 - 9.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `916` | 5 - 9.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `920` | 10 - 19.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `921` | 10 - 19.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `922` | 10 - 19.99 ACRES; RES | neighborhood.csv |
| `923` | 10 - 19.99 ACRES; 2+ RES | neighborhood.csv |
| `924` | 10 - 19.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `926` | 10 - 19.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `930` | 20 - 79.99 ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `931` | 20 - 79.99 ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `932` | 20 - 79.99 ACRES; RES | neighborhood.csv |
| `933` | 20 - 79.99 ACRES; 2+ RES | neighborhood.csv |
| `934` | 20 - 79.99 ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `936` | 20 - 79.99 ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `940` | 80+ ACRES; NO IMPROVEMENTS | neighborhood.csv |
| `941` | 80+ ACRES; OTHER IMPROVEMENTS | neighborhood.csv |
| `942` | 80+ ACRES; RES | neighborhood.csv |
| `943` | 80+ ACRES; 2+ RES | neighborhood.csv |
| `944` | 80+ ACRES; MOBILE/MANF. HOME | neighborhood.csv |
| `946` | 80+ ACRES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `96` | FOREST LAND | neighborhood.csv |
| `960` | CLASSIFIED FOREST LAND; NO IMPROVEMENTS | neighborhood.csv |
| `961` | BLDG ONLY LOCATED ON CF | neighborhood.csv |
| `970` | DESIGNATED FOREST LAND; NO IMPROVEMENTS | neighborhood.csv |
| `971` | BLDG ONLY LOCATED ON DF | neighborhood.csv |
| `990` | TAX EXEMPT PROPERTIES; NO IMPROVEMENTS | neighborhood.csv |
| `991` | TAX EXEMPT PROPERTIES; OTHER IMPROVEMENTS | neighborhood.csv |
| `992` | TAX EXEMPT PROPERTIES; RES | neighborhood.csv |
| `993` | TAX EXEMPT PROPERTIES; 2+ RES | neighborhood.csv |
| `994` | TAX EXEMPT PROPERTIES; MOBILE/MANF. HOME | neighborhood.csv |
| `996` | TAX EXEMPT PROPERTIES; COMMERCIAL IMPROVEMENT | neighborhood.csv |
| `TEST` | THIS IS A TEST | neighborhood.csv |
