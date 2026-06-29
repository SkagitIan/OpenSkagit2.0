# Skagit County Area Zoning Allowed-Use Tables

This file is meant to be handed to an AI agent as a plain Markdown zoning reference.

Scope: Skagit County proper plus incorporated jurisdictions inside Skagit County.

Style: Skagit-style allowed-use tables and zone-by-zone use lists.

This is a source-backed working compile. Empty cells mean the use was not shown as allowed in the source table, or that the row has not yet been fully extracted from that jurisdiction. Do not guess missing cells.

---

## Permission Code Key

| Code | Meaning |
|---|---|
| P | Permitted use |
| AC | Accessory use |
| AD | Administrative special use / administrative review |
| HE | Hearing Examiner special use |
| C | Conditional use |
| CUP | Conditional use permit |
| X | Prohibited |
| blank | Not shown as allowed, not extracted, or prohibited depending on the local code |

---

## Source Register

| Jurisdiction | Source Located | Extraction Status |
|---|---|---|
| Skagit County | SCC Title 14, especially Ch. 14.11, 14.12, 14.13, 14.15, 14.16 | Rural Mixed-Use table extracted; additional county tables partially noted |
| Anacortes | AMC Title 19, Ch. 19.41 use tables | Residential table extracted from available PDF/table source |
| Burlington | BMC Title 17 Comprehensive Zoning Ordinance | RA-1, MUR-1, MUC-1 extracted in list/table form; remaining zones pending |
| Mount Vernon | MVMC Title 17 Zoning | Source located; extraction pending |
| Sedro-Woolley | SWMC Title 17 Zoning | Several major zones extracted from source/mirror text; remaining zones pending |
| Concrete | CMC Title 19, Ch. 19.15 land use table | Major table rows extracted |
| Hamilton | Town ordinances / zoning ordinance materials | Source not cleanly extracted yet |
| La Conner | LCMC Title 15 Uniform Development Code | Source located; extraction pending |
| Lyman | Town zoning code PDF and zoning map | Source located; PDF extraction pending |

---

# 1. Skagit County

## 1.1 Rural Mixed-Use Zones

Source table: `Table 14.11.020-1 Allowed Uses in the Rural Mixed-Use Zones`

Zone columns:

| Code | Zone |
|---|---|
| RI | Rural Intermediate |
| RRv | Rural Reserve |
| RVR | Rural Village Residential |
| RC | Rural Center |
| RVC | Rural Village Commercial |
| RVC Alger | Rural Village Commercial - Alger |
| OSRSI | Public Open Space of Regional/Statewide Importance |

### Residential Uses

| Use | RI | RRv | RVR | RC | RVC | RVC Alger | OSRSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single-family residence | P | P | P |  |  |  |  |
| Accessory dwelling unit | P | P | P |  |  |  |  |
| Middle housing (2-4 units) |  |  | P |  |  |  |  |
| Co-housing as part of a CaRD | P | P | P |  |  |  |  |
| Loft living quarters |  |  |  | P | P | P |  |
| Owner operator/caretaker quarters |  |  |  | AC | AC | AC |  |
| Emergency housing |  |  |  |  | P |  |  |
| Emergency shelter |  |  |  |  | P |  |  |
| Manufactured or mobile home park |  |  | P |  |  |  |  |
| Permanent supportive housing |  |  | P |  |  |  |  |
| Residential accessory use | P | P | P |  |  |  |  |
| Seasonal worker housing | HE | HE |  |  |  |  |  |
| Transitional housing |  |  | P |  | P |  |  |
| Temporary manufactured home | P | P | P |  |  |  |  |

### Commercial/Retail Uses

| Use | RI | RRv | RVR | RC | RVC | RVC Alger | OSRSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Animal clinic/hospital | HE | HE |  | HE | AD | AD |  |
| Animal preserve |  | HE |  |  |  |  | HE |
| Asphalt/concrete batching or recycling, temporary |  | HE |  |  |  |  |  |
| Bed and breakfast | AD | AD | AD | P |  |  |  |
| Business/professional office |  |  |  |  | P |  |  |
| Display gardens |  | HE |  |  |  |  |  |
| Family day care provider | P | P | P | P | P | P |  |
| Fish hatchery | HE | HE |  |  |  |  |  |
| Group care facility | HE |  |  | HE |  |  |  |
| Group care facility, adult | HE |  |  |  | AD | AD |  |
| Home-Based Business 1 | P | P | P |  |  |  |  |
| Home-Based Business 2 | AD | AD | AD |  |  |  |  |
| Home-Based Business 3 | HE | HE | HE |  |  |  |  |
| Kennel, boarding | HE | HE | HE | AD | AD | AD |  |
| Kennel, day-use | HE | AD | HE | P | P | P |  |
| Kennel, limited | HE | HE | HE |  |  |  |  |
| Laundromat |  |  |  |  |  | P |  |
| Limited event venues / temporary events | AD | AD | AD | AD | AD | AD | AD |
| Marijuana retail facility |  |  |  | AD | AD | AD |  |
| Marina, ≤20 slips | HE |  |  |  | HE |  | HE |
| Marina, >20 slips |  |  |  |  |  |  |  |
| Mini-storage |  |  |  | P | P | P |  |
| Mortuary | HE |  |  |  | HE |  |  |
| Outpatient medical and health care service |  |  | HE | P | P | P |  |
| Overnight lodging and related services for visitors to the rural area |  |  |  |  | P | P |  |
| Restaurant |  |  |  | P | P | P |  |
| Small retail and service business |  |  |  | P | P | P |  |
| Small-scale production or manufacture |  |  |  |  | AD | AD |  |

### Community/Public Uses

| Use | RI | RRv | RVR | RC | RVC | RVC Alger | OSRSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cemetery | HE | HE | HE |  |  |  |  |
| Church | HE | HE | HE | HE | HE |  |  |
| Community club/grange hall | HE | HE | HE | P | P | P |  |
| Conference center |  |  |  |  |  |  |  |
| Historic site open to the public | HE | HE | HE | P | P | P | P |
| Interpretive/information center |  |  |  |  |  |  | P |
| Museum |  |  |  |  |  |  | P |
| Pre-school | HE | HE |  | P | P | P |  |

### Natural Resource Uses

| Use | RI | RRv | RVR | RC | RVC | RVC Alger | OSRSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Agriculture | P | P |  |  |  |  |  |
| Agricultural accessory use | P | P |  |  |  |  |  |
| Agricultural processing facility |  | P |  |  |  |  |  |
| Anaerobic digester | HE |  |  |  |  |  |  |
| Fish hatchery | HE |  |  |  |  |  |  |
| Forestry | P | P |  |  |  |  |  |
| Habitat enhancement/restoration project | P | P | P | P |  |  |  |
| Manure lagoon | HE |  |  |  |  |  |  |
| Natural resource support services | P | P |  |  |  |  |  |
| Natural resources training/research facility | HE |  |  |  |  |  |  |
| Nursery/greenhouse, retail | HE | X |  | P | AD | AD |  |
| Nursery/greenhouse, wholesale | HE | P |  |  |  |  |  |
| Seasonal roadside stand ≤300 sf | P | P | P | P | P | P |  |
| Seasonal roadside stand >300 sf | HE | HE |  | AD | AD |  |  |

### Park/Recreational Uses

| Use | RI | RRv | RVR | RC | RVC | RVC Alger | OSRSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Campground, destination |  |  |  |  | AD |  | AD |
| Campground, developed |  |  |  |  | HE |  | AD |
| Campground, primitive |  |  |  |  | AD |  | AD |
| Golf course | HE |  |  |  |  |  |  |
| Off-road vehicle use areas and trails |  |  |  |  |  |  | HE |
| Outdoor outfitters enterprise |  |  |  |  |  |  | HE |
| Outdoor recreational facility | HE | HE |  |  | AD |  |  |
| Outdoor recreational equipment rental and/or guide services |  |  |  |  |  |  |  |
| Park, community | HE | HE | HE | HE |  |  |  |
| Park, recreation open space |  |  |  |  |  |  | AD |
| Park, regional |  |  |  |  | AD |  | AD |
| Park, specialized recreational area | AD | AD | AD | AD | AD | AD |  |
| Racetrack, recreational |  |  |  |  |  |  | HE |
| Shooting club, indoor |  |  |  | HE | HE |  |  |
| Shooting club, outdoor |  |  |  |  |  |  | HE |
| Stables and riding club | HE | HE |  |  | AD |  |  |
| Trail | AD | AD | AD | AD | AD |  | P |
| Trailhead, primary and secondary | AD | AD | AD | AD | AD | AD | AD |

### Storage, Transportation, and Utility Uses

| Use | RI | RRv | RVR | RC | RVC | RVC Alger | OSRSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Outdoor storage 1 |  |  |  |  | AD |  |  |
| Outdoor storage 2 |  |  |  |  | AD |  |  |
| Outdoor storage 3 |  |  |  |  | HE |  |  |
| Outdoor storage 4 |  |  |  |  | HE |  |  |
| Aircraft landing field | HE |  |  |  |  |  |  |
| Vehicle charging station |  |  |  | P | P | P | AC |
| Vehicle fueling station |  |  |  | P | P | P |  |
| Impoundment | HE |  |  |  |  |  |  |
| Impoundment >1 acre-foot | HE | HE |  |  |  |  |  |
| Recycling drop-box facility |  |  | AC | AC | AC | P | P |
| Water diversion structure |  |  |  |  |  |  | AD |

---

## 1.2 Skagit County Rural Commercial/Industrial Zones

Source table: `Table 14.12.020-1 Allowed Uses in the Rural Commercial/Industrial Zones`

Zone columns: `RB`, `RFS`, `SSB`, `NRI`, `RMI`, `SRT`

Extraction status: partial only.

| Use | RB | RFS | SSB | NRI | RMI | SRT |
|---|---:|---:|---:|---:|---:|---:|
| Owner operator/caretaker quarters | AC | AC | AC | AC | AC | AC |
| Animal clinic/hospital | P |  |  |  |  |  |
| Animal preserve |  |  |  |  |  | HE |
| Asphalt/concrete batching or recycling, permanent |  |  |  | HE |  |  |
| Asphalt/concrete batching or recycling, temporary |  |  |  | HE |  |  |
| Bed and breakfast | P |  |  |  |  |  |
| Billboard | AD |  |  | HE |  |  |
| Business/professional office | P | P | AC |  |  |  |
| Car wash |  | P |  |  |  |  |
| Commercial boathouse |  |  |  |  | P |  |
| Display gardens | P |  |  |  |  |  |
| Hotel/motel |  | HE |  |  |  |  |
| Institutional camp/retreat |  |  |  |  |  | P |
| Kennel, boarding | AD |  | HE | AD |  |  |
| Kennel, day-use | P |  | AD | P |  |  |
| Kennel, limited | HE |  |  |  |  |  |

---

# 2. Anacortes

## 2.1 Residential Zones

Source table: `AMC 19.41.040 Principal Uses Permitted in Residential Zones`

Zone columns: `R1`, `R2`, `R2A`, `R3`, `R3A`, `R4`, `R4A`, `OT`

### Residential / Household Living

| Use | R1 | R2 | R2A | R3 | R3A | R4 | R4A | OT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Single-family | P | P | P | P | P | P | P | P |
| Single-family, small lot |  |  |  | P | P | P | P |  |
| Cottage housing |  | P | P | P | P | P | P |  |
| Duplex |  | P | P | P | P | P | P | P |
| Triplex |  |  |  | P | P | P | P |  |
| Townhouse |  |  |  | P | P | P | P |  |
| Multifamily, 4 units |  |  |  | P | P | P | P |  |
| Multifamily, 5 or more units |  |  |  |  |  | P | P |  |
| Live-work |  |  |  |  |  |  |  |  |
| Adult family home | P | P | P | P | P | P | P | P |
| Assisted living facility |  |  |  | C | C | P | C |  |
| Nursing homes |  |  |  |  |  | C |  |  |
| Rooming houses |  |  |  | C | C | P | P | C |

### Civic, Commercial, and Other Principal Uses in Residential Zones

| Use | R1 | R2 | R2A | R3 | R3A | R4 | R4A | OT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Day care I facilities | P | P | P | P | P | P | P | P |
| Day care II facilities |  |  | C | C | C | P | C | C |
| Public safety facility | C | C | C | C | C | C | C | C |
| Medical, except as listed below |  |  |  | C | C |  |  |  |
| Hospital |  |  |  |  |  |  |  |  |
| Office |  |  |  |  |  |  |  |  |
| Bed and breakfast | C | C | C | C | C | P | P | C |
| Parking | C | C | C | C | C | C | C | C |
| Passenger terminal |  |  |  |  |  |  |  |  |
| Beauty salons |  |  |  |  |  | C | C |  |
| Recreation, indoor |  |  |  |  |  |  |  |  |
| Recreation, outdoor |  |  |  |  |  |  |  |  |
| Restaurant/bar |  |  |  |  |  |  |  |  |
| Retail sales |  |  |  |  |  |  |  |  |
| Neighborhood grocery store |  | C | C | C | C | C | C | C |
| Vehicle sales/rental |  |  |  |  |  |  |  |  |

---

# 3. Burlington

Burlington uses zone-by-zone allowed-use sections rather than one single master matrix.

Known Title 17 zone groups include `RD`, `RA`, `MUR`, `MUC`, `CI`, `PC`, `PFT`, and `UH`.

Extraction status: RA-1, MUR-1, and MUC-1 extracted below. Remaining zones pending.

## 3.1 RA-1 Residential Attached Zone

| Use | Status |
|---|---:|
| Duplex dwellings | P |
| Horizontally attached dwellings | P |
| Small multiunit buildings | P |
| Detached dwellings | P |
| Small boarding houses | P |
| Small commercial child day care center | P |
| Small utilities | P |
| Normal residential appurtenances | AC |
| Household pets | AC |
| Family day care | AC |
| Foster family care | AC |
| Accessory dwelling units | AC |
| Urban agriculture | AC |
| Telecommunications microfacility | AC |
| Large boarding houses | C |
| Medium multiunit buildings | C |
| Small meeting facilities | C |
| Small private schools | C |
| Large commercial child day care centers | C |
| Medium utilities | C |
| Accessory buildings with footprint greater than 800 square feet | C |
| Small nursing homes | C |

## 3.2 MUR-1 Mixed Use Residential Zone

| Use | Status |
|---|---:|
| Detached dwellings | P |
| Duplex dwellings | P |
| Horizontally attached dwellings | P |
| Small multiunit buildings | P |
| Medium multiunit buildings | P |
| Boarding houses | P |
| Commercial child day care centers, all sizes | P |
| Small utilities | P |
| Small private schools | P |
| Small meeting facilities | P |
| Professional offices | P |
| Personal services | P |
| Specialized instruction | P |
| Small nursing homes | P |
| Small scale retail | P |
| Small healthcare facilities | P |
| Veterinary clinics | P |
| Large meeting facilities | C |
| Large private schools | C |
| Medium utilities | C |
| Large multiunit buildings | C |
| Small eating/drinking establishments | C |
| Medium scale retail | C |
| Large nursing homes | C |
| Large healthcare facilities | C |

## 3.3 MUC-1 Mixed Use Commercial Zone

| Use | Status |
|---|---:|
| Offices, all types | P |
| Multiunit buildings, all sizes | P |
| Dwellings in mixed-use buildings | P |
| Retail, small and medium scale | P |
| Hotels | P |
| Healthcare facilities, all sizes | P |
| Eating/drinking establishments, all sizes | P |
| Specialized instruction | P |
| Theaters | P |
| Child care centers, all sizes | P |
| Meeting facilities, all sizes | P |
| Horizontally attached dwellings | P |
| Private schools, all sizes | P |
| Small utilities | P |
| Personal services | P |
| Nursing homes, all sizes | P |
| Veterinary clinics | P |
| Emergency housing | P |
| Duplexes, with restrictions | C |
| Minor indoor commercial entertainment | C |
| Medium utilities | C |
| Craft industries | C |
| Large retail | C |
| Laboratories/research | C |
| Small scale indoor commercial entertainment | C |
| Buildings greater than 6,000 square feet | C |

---

# 4. Sedro-Woolley

Sedro-Woolley uses zone-by-zone use restriction sections.

Extraction status: major zones extracted below. Remaining public/open-space/special zones pending.

## 4.1 Residential Zones Summary Matrix

| Use | R-1 | R-5 | R-7 | R-15 |
|---|---:|---:|---:|---:|
| One single-family residence per lot | P | P | P | P |
| Low-intensity agriculture | P | P | P | P |
| Home occupations | P | P | P | P |
| Child day care centers meeting state requirements | P | P | P | P |
| Adult or family day care facilities meeting state requirements | P | P | P | P |
| Accessory dwelling units | P | P | P | P |
| One duplex per lot |  |  | P |  |
| Multifamily residential developments up to 8 dwelling units |  |  |  | P |
| Multifamily residential developments up to 12 dwelling units |  |  |  | P |
| Public uses | C | C | C | C |
| Quasi-public uses | C | C | C | C |
| Recreational uses, not including parks | C | C | C | C |
| Home occupation employing nonresidents | C | C | C | C |
| Cemeteries | C | C | C | C |
| Veterinary clinics and kennels |  |  |  | C |
| Transmission towers and similar structures | C | C | C | C |
| Essential public facilities | C | C | C | C |
| Uses not listed | X | X | X | X |

## 4.2 Mixed Commercial Zone

| Use | Status |
|---|---:|
| Retail sales | P |
| General services | P |
| Recreational uses | P |
| Cultural uses | P |
| Light manufacturing | P |
| Low-intensity agriculture | P |
| Multifamily residential, located above the first story of a commercial building | P |
| Professional offices | P |
| Residential uses existing prior to zone adoption | P |
| Public uses | C |
| Quasi-public uses | C |
| Essential public facilities | C |
| Residential use of the first story of commercial buildings | C |
| Uses not listed | X |

## 4.3 Central Business District

| Use | Status |
|---|---:|
| Retail sales | P |
| General services | P |
| Professional offices | P |
| Cultural uses | P |
| Public uses/facilities | P |
| Recreational uses | P |
| Multifamily residential, located above the first story of a commercial building | P |
| Quasi-public uses | C |
| Essential public facilities | C |
| Residential use of the first story of commercial buildings | C |
| Uses not listed | X |

## 4.4 Industrial Zone

| Use | Status |
|---|---:|
| Manufacturing | P |
| Warehousing | P |
| Distribution | P |
| Processing | P |
| Assembly | P |
| Transportation-related uses | P |
| Wholesale uses | P |
| Storage yards | P |
| Contractor yards | P |
| Light industrial uses | P |
| Heavy industrial uses, subject to standards | P |
| Adult entertainment uses, subject to restrictions | P |
| Public uses | C |
| Quasi-public uses | C |
| Essential public facilities | C |
| Uses not listed | X |

---

# 5. Concrete

Source table: `CMC 19.15.020 Land Use Table`

Zone columns:

| Code | Zone |
|---|---|
| R | Residential |
| A | Aviation |
| CL | Commercial-Light |
| TC | Town Center |
| I | Industrial |
| P | Public |
| OS | Open Space |

## 5.1 Residential Uses

| Use | R | A | CL | TC | I | P | OS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single-family detached per lot | P |  |  |  |  |  | P |
| Caretaker apartment/quarters, not more than one per establishment |  |  | P | P | P |  |  |
| Aviation-related single-unit apartment |  | P |  |  |  |  |  |
| Accessory dwelling unit | P |  |  |  |  |  |  |
| Duplex/triplex/fourplex | P |  |  |  |  |  |  |
| Fiveplex/sixplex | C |  | C | P |  |  |  |
| Townhouse/stacked flats/courtyard buildings | C |  | C | P |  |  |  |
| Cottage houses | C |  |  |  |  |  |  |
| Co-living housing units | C |  | C | C |  |  |  |
| Mixed-use | C |  | P | P |  |  |  |
| Planned unit developments | C |  |  |  |  |  |  |
| Affordable housing | P |  | P | P |  |  |  |
| Permanent supportive housing | P |  | P | P |  |  |  |
| Transitional housing | C |  | C | C |  |  |  |
| Emergency housing and emergency shelters | C |  | C | C |  |  |  |
| Encampments on religious property | C |  | C | C |  |  |  |
| Group homes, including handicapped | C |  |  |  |  |  |  |
| Nursing homes |  |  | P | P |  |  |  |
| Motels |  |  | P | P | C |  |  |
| Hotels |  |  | P | P |  |  |  |
| Mobile and manufactured home parks |  |  | C |  |  |  |  |
| Recreation vehicle park |  |  | C |  |  | C |  |
| Accessory uses | P |  |  |  |  |  | P |
| Home occupations / sole proprietor businesses | P |  |  |  |  |  |  |
| Household pets | P |  |  |  |  |  | P |

## 5.2 Aviation Uses

| Use | R | A | CL | TC | I | P | OS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aviation hangar, one per lot |  | P |  |  |  |  |  |
| Aviation-related commercial/industrial uses |  | P |  |  |  |  |  |
| Aviation-related public uses |  | P |  |  |  |  |  |
| Aviation-related commercial uses |  | C |  |  |  |  |  |
| Aviation-related manufacturing uses |  | C |  |  |  |  |  |
| Aviation-related service business, such as restaurants |  | C |  |  |  |  |  |
| Airports and related uses |  |  |  |  |  | C |  |

## 5.3 Commercial Uses

| Use | R | A | CL | TC | I | P | OS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Accessory buildings / multi-building development |  |  | P | P |  |  |  |
| Administrative, educational, and related |  |  | P |  |  |  |  |
| Arcades |  |  | C | C |  |  |  |
| Automobile sales and leasing |  |  | P | C |  |  |  |
| Automobile service stations |  |  | P | C |  |  |  |
| Art/music/photo studios |  |  | P | P |  |  |  |
| Baking bread/pastry sold on premises |  |  | P | P |  |  |  |
| Banking/financial institutions |  |  | P | P | C |  |  |
| Bingo halls |  |  |  |  | P |  |  |
| Club, topless |  |  |  |  | P |  |  |
| Convenience stores |  |  | P | P |  |  |  |
| Convenience grocery stores |  |  |  |  | P |  |  |
| Day care, family and child centers | C |  | P | C | C |  |  |
| Day care, adult/family | P |  |  |  |  |  |  |
| Day care on-site of specified permitted use |  |  |  |  | P |  |  |
| Delicatessens |  |  | P | P | C |  |  |
| Drive-in facilities, including banks and restaurants |  |  |  | C |  |  |  |
| Dry cleaning and laundry services |  |  | P | P | P |  |  |
| Eating establishments limited to on-site employers |  |  |  |  | P |  |  |
| Factory outlets |  |  | P |  |  |  |  |
| Food banks |  |  | C | C |  |  |  |
| Funeral homes |  |  | P | P |  |  |  |
| Grocery stores |  |  | P | P | C |  |  |
| Health/fitness clubs |  |  |  |  | P |  |  |
| Hobby shops |  |  | P | P |  |  |  |
| Household goods storage |  |  | P | C |  |  |  |
| Hospitals, including small animals |  |  | P | P |  |  |  |
| Kennels | C |  |  |  |  |  |  |
| Laundry, self-service |  |  | P | P | P |  |  |
| Laundries, commercial |  |  |  |  | P |  |  |
| Liquor store |  |  | P | P |  |  |  |
| Manufactured/mobile home sales lots |  |  |  |  | C |  |  |
| News syndicate services |  |  | P | P |  |  |  |
| Newsstands |  |  | P | P |  |  |  |
| Personal service shops |  |  | P | P | C |  |  |
| Pharmacies |  |  | P | P |  |  |  |
| Printing/publishing |  |  | P | P |  |  |  |
| Professional offices, including headquarters |  |  | P | P | C |  |  |
| Radio/TV broadcasting studios |  |  | P | P | C |  |  |
| Recreation, commercial |  |  |  |  | C |  |  |
| Recreational vehicle sales lots |  |  |  |  | P |  |  |
| Retail sales |  |  |  |  | C |  |  |
| Retail stores, including department/variety |  |  | P | P |  |  |  |
| Research laboratories |  |  | P |  |  |  |  |
| Restaurants, including outdoor eating |  |  | P | P | C |  |  |
| Secretarial services |  |  | P | P | C |  |  |
| Taverns/dance halls/music auditorium |  |  | C | C | C |  |  |
| Theaters, except drive-in |  |  | P | P |  |  |  |
| Theaters, drive-in |  |  |  |  | C |  |  |
| Vehicle repair shops within enclosed building |  |  | P |  |  |  |  |
| Water bottling facilities |  |  | P |  |  |  |  |

## 5.4 Industrial Uses

| Use | R | A | CL | TC | I | P | OS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sale/repair of firearms |  |  | C |  |  |  |  |
| Mini-storage warehouses |  |  | C |  | P |  |  |
| Animal/food processing |  |  |  |  | C |  |  |
| Auction houses, including animals |  |  |  |  | C |  |  |
| Automobile/truck rental |  |  |  |  | P |  |  |
| Automobile/truck sales, new/used |  |  |  |  | P |  |  |
| Auto repair shops enclosed |  |  | P |  |  |  |  |
| Automobile repair services |  |  |  |  | P |  |  |
| Automobile service station |  |  |  |  | P |  |  |
| Basic wood processing |  |  |  |  | P |  |  |
| Boat building/accessory fabrication |  |  |  |  | P |  |  |
| Building movers |  |  |  |  | P |  |  |
| Bulk storage/processing |  |  |  |  | C |  |  |
| Cold storage plants |  |  |  |  | P |  |  |
| Concrete mixing/batching plants |  |  |  |  | C |  |  |
| Contractor trade services, including storage yards |  |  |  |  | P |  |  |
| Enameling/galvanizing/electroplating |  |  |  |  | P |  |  |
| Equipment repair/storage/rental/leasing/sales |  |  |  |  | P |  |  |
| Existing logging company |  |  | P |  | P |  |  |
| Food locker services |  |  |  |  | P |  |  |
| Heavy equipment/truck repair |  |  |  |  | P |  |  |
| Household movers/storage |  |  |  |  | P |  |  |
| Janitorial services |  |  |  |  | P |  |  |
| Lumber yards |  |  |  |  | P |  |  |
| Manufacturing, light |  |  | P |  |  |  |  |
| Manufacturing, natural materials/electronics/appliances/metals/soaps/clay/drugs/food/computers |  |  |  |  | P |  |  |
| Motorcycle sales/services |  |  |  |  | P |  |  |
| Motor freight terminals/transportation |  |  |  |  | P |  |  |
| Offices related to on-site permitted use |  |  |  |  | P |  |  |
| Outside storage yards |  |  |  |  | P |  |  |
| Printing/publishing/allied |  |  |  |  | P |  |  |
| Radio/TV transmitting towers |  |  |  |  | C |  |  |
| Research/development/testing of permitted use |  |  |  |  | P |  |  |
| Retail/wholesale trade of products manufactured/processed/assembled on-site |  |  |  |  | P |  |  |
| Rock crushing plants |  |  |  |  | C |  |  |
| Small appliance repair |  |  |  |  | C |  |  |
| Theaters, adult |  |  |  |  | P |  |  |
| Upholstery/furniture repair |  |  |  |  | C |  |  |
| Warehouse sales open to public |  |  |  |  | C |  |  |
| Warehousing/distribution/wholesale trade not open to public |  |  |  |  | P |  |  |

## 5.5 Public and Open Space Uses

| Use | R | A | CL | TC | I | P | OS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Agriculture croplands |  |  |  |  |  |  | P |
| Civic/social/fraternal clubs |  |  | P | P | P |  |  |
| Conservation areas, including forest/wetlands/wildlife |  |  |  |  |  | P | P |
| Community centers |  |  |  |  |  | P | P |
| Clubhouses/youth centers |  |  |  |  |  | C |  |
| Golf courses/country clubs, privately owned | C |  |  |  |  |  |  |
| Golf courses/clubhouses, publicly owned |  |  |  |  |  | C | C |
| Government facilities | C |  | C | C | C |  |  |
| Government facilities, fire stations |  |  | P |  |  |  |  |
| Government municipal buildings/structures/facilities |  |  |  |  |  | P |  |
| Meeting rooms/recreation facilities |  |  | P | P |  |  |  |
| Museums/libraries/public schools |  |  |  |  |  | P |  |
| Parks/trails/playgrounds | P |  | P |  |  | P | P |
| Public parks/scenic areas/trails |  |  |  |  |  | P | P |
| Reclamation areas |  |  |  |  |  | P | P |
| Schools |  |  | P | P |  |  |  |
| Schools, existing | P |  |  |  |  |  |  |
| Schools, preschools/nursery |  |  | P | C | C |  |  |
| Schools, job training/vocational |  |  |  |  | P |  |  |
| Recreation buildings/neighborhood facilities | C |  |  |  |  |  |  |
| Recreation on-site facilities serving specified use |  |  |  |  | P |  |  |
| Religious institutions | C |  | P | C |  | C |  |

## 5.6 Infrastructure Uses

| Use | R | A | CL | TC | I | P | OS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bus passenger terminals |  |  |  |  | P |  |  |
| Hydroelectric power generation facilities |  |  |  |  |  |  | C |
| Parking facilities |  |  | P | C |  |  |  |
| Parking facilities for permitted uses on-site |  |  |  |  |  | P | P |
| Utility substations / public utility facilities | C |  |  | C |  | C | C |
| Utility facilities, major |  |  | C |  |  |  |  |
| Utility facilities, minor |  |  | P |  |  |  |  |
| Utility substations unless incidental permitted use |  |  |  |  | C |  |  |
| Wireless communications facilities |  |  | C |  |  |  |  |

---

# 6. Mount Vernon

Source located: `Title 17 Zoning`

Extraction status: pending.

Do not infer Mount Vernon allowed-use cells from Skagit County or another city. Mount Vernon needs its own extraction by chapter.

Known zoning chapters from source include residential, commercial, industrial, public, and special districts. The next extraction pass should convert each chapter's permitted, accessory, conditional, and prohibited-use sections into tables like the ones above.

---

# 7. La Conner

Source located: `Title 15 Uniform Development Code`

Extraction status: pending.

Do not infer La Conner allowed-use cells from another jurisdiction. La Conner needs extraction from its residential, commercial, transitional commercial, industrial, port industrial, public use, and historic preservation sections.

---

# 8. Lyman

Source located: Town zoning code PDF and zoning map download page.

Extraction status: pending because the PDF needs separate text/table extraction.

Do not infer Lyman allowed-use cells from Skagit County or another town.

---

# 9. Hamilton

Extraction status: pending.

A clean current use matrix was not extracted in this pass. Hamilton appears to require ordinance/PDF review before use rows can be filled safely.

---

# 10. Notes for Agent Use

Use this file only as a zoning allowed-use reference.

When answering a parcel-use question, the agent should:
1. Determine the parcel jurisdiction.
2. Determine the parcel zoning district.
3. Look up the use row in that jurisdiction's table.
4. Return the status shown in the cell.
5. If the jurisdiction or use is marked pending, say the use table has not been extracted yet.

Do not create new statuses. Do not score statuses. Do not fill blanks from another jurisdiction.
