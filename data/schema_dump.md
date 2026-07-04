## r2://openskagit/assessor.parquet

| column_name                 | column_type   | null   | key   | default   | extra   |
|:----------------------------|:--------------|:-------|:------|:----------|:--------|
| AID                         | VARCHAR       | YES    |       |           |         |
| Parcel Number               | VARCHAR       | YES    |       |           |         |
| Account Number              | VARCHAR       | YES    |       |           |         |
| Legal Description           | VARCHAR       | YES    |       |           |         |
| Situs Street Number         | VARCHAR       | YES    |       |           |         |
| Situs Street Name           | VARCHAR       | YES    |       |           |         |
| Situs City State Zip        | VARCHAR       | YES    |       |           |         |
| Old Street Number           | VARCHAR       | YES    |       |           |         |
| Old Street Name             | VARCHAR       | YES    |       |           |         |
| Old City State Zip          | VARCHAR       | YES    |       |           |         |
| Owner Name                  | VARCHAR       | YES    |       |           |         |
| Owner Add 1                 | VARCHAR       | YES    |       |           |         |
| Owner Add 2                 | VARCHAR       | YES    |       |           |         |
| Owner Add 3                 | VARCHAR       | YES    |       |           |         |
| Owner City                  | VARCHAR       | YES    |       |           |         |
| Owner State                 | VARCHAR       | YES    |       |           |         |
| Owner Zip                   | VARCHAR       | YES    |       |           |         |
| Exemptions                  | VARCHAR       | YES    |       |           |         |
| Neighborhood Code           | VARCHAR       | YES    |       |           |         |
| Building Value              | VARCHAR       | YES    |       |           |         |
| Land Use                    | VARCHAR       | YES    |       |           |         |
| Impr Land Value             | VARCHAR       | YES    |       |           |         |
| Unimpr Land Value           | VARCHAR       | YES    |       |           |         |
| Timber Land Value           | VARCHAR       | YES    |       |           |         |
| Assessed Value              | VARCHAR       | YES    |       |           |         |
| Taxable Value               | VARCHAR       | YES    |       |           |         |
| Total Market Value          | VARCHAR       | YES    |       |           |         |
| Acres                       | VARCHAR       | YES    |       |           |         |
| Sale Date                   | VARCHAR       | YES    |       |           |         |
| Sale Price                  | VARCHAR       | YES    |       |           |         |
| Sale Deed Type              | VARCHAR       | YES    |       |           |         |
| Total Taxes                 | VARCHAR       | YES    |       |           |         |
| Year Built                  | VARCHAR       | YES    |       |           |         |
| Living Area                 | VARCHAR       | YES    |       |           |         |
| Tot Special Assessments     | VARCHAR       | YES    |       |           |         |
| General Taxes               | VARCHAR       | YES    |       |           |         |
| Inactive Date               | VARCHAR       | YES    |       |           |         |
| BuildingStyle               | VARCHAR       | YES    |       |           |         |
| Foundation                  | VARCHAR       | YES    |       |           |         |
| Exterior Walls              | VARCHAR       | YES    |       |           |         |
| Roof Covering               | VARCHAR       | YES    |       |           |         |
| Roof Style                  | VARCHAR       | YES    |       |           |         |
| Floor Covering              | VARCHAR       | YES    |       |           |         |
| Floor Construction          | VARCHAR       | YES    |       |           |         |
| Interior Finish             | VARCHAR       | YES    |       |           |         |
| Plumbing                    | VARCHAR       | YES    |       |           |         |
| GarageSqFt                  | VARCHAR       | YES    |       |           |         |
| Heat Air Cond               | VARCHAR       | YES    |       |           |         |
| Fireplace                   | VARCHAR       | YES    |       |           |         |
| FinishedBasement            | VARCHAR       | YES    |       |           |         |
| Number of Bedrooms          | VARCHAR       | YES    |       |           |         |
| Eff Year Built              | VARCHAR       | YES    |       |           |         |
| UnfinishedBasement          | VARCHAR       | YES    |       |           |         |
| Fire District               | VARCHAR       | YES    |       |           |         |
| School District             | VARCHAR       | YES    |       |           |         |
| City District               | VARCHAR       | YES    |       |           |         |
| Unit                        | VARCHAR       | YES    |       |           |         |
| Levy Code                   | VARCHAR       | YES    |       |           |         |
| Current Use Adjustment      | VARCHAR       | YES    |       |           |         |
| Tide Land Value             | VARCHAR       | YES    |       |           |         |
| Senior Exemption Adjustment | VARCHAR       | YES    |       |           |         |
| Township                    | VARCHAR       | YES    |       |           |         |
| Range                       | VARCHAR       | YES    |       |           |         |
| Section                     | VARCHAR       | YES    |       |           |         |
| Quarter Section             | VARCHAR       | YES    |       |           |         |
| Tax Year                    | VARCHAR       | YES    |       |           |         |
| Appraisal Year              | VARCHAR       | YES    |       |           |         |
| Utilities                   | VARCHAR       | YES    |       |           |         |
| Tax Statement Taxable Value | VARCHAR       | YES    |       |           |         |
| PropType                    | VARCHAR       | YES    |       |           |         |
| HasSeptic                   | VARCHAR       | YES    |       |           |         |

## r2://openskagit/derived/parcel_geo_flags.parquet

| column_name                     | column_type   | null   | key   | default   | extra   |
|:--------------------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number                   | VARCHAR       | YES    |       |           |         |
| gis_x                           | DOUBLE        | YES    |       |           |         |
| gis_y                           | DOUBLE        | YES    |       |           |         |
| has_geometry                    | BOOLEAN       | YES    |       |           |         |
| pnumber_record_count            | BIGINT        | YES    |       |           |         |
| comp_plan_lud                   | VARCHAR       | YES    |       |           |         |
| zoning_code_short               | VARCHAR       | YES    |       |           |         |
| zoning_label                    | VARCHAR       | YES    |       |           |         |
| zoning_code                     | VARCHAR       | YES    |       |           |         |
| comp_plan_hit_count             | BIGINT        | YES    |       |           |         |
| city_name                       | VARCHAR       | YES    |       |           |         |
| inside_city_limits              | BOOLEAN       | YES    |       |           |         |
| city_hit_count                  | BIGINT        | YES    |       |           |         |
| fire_district                   | VARCHAR       | YES    |       |           |         |
| fire_district_hit_count         | BIGINT        | YES    |       |           |         |
| school_district_num             | VARCHAR       | YES    |       |           |         |
| school_district_name            | VARCHAR       | YES    |       |           |         |
| school_district_hit_count       | BIGINT        | YES    |       |           |         |
| commissioner_district           | VARCHAR       | YES    |       |           |         |
| commissioner_name               | VARCHAR       | YES    |       |           |         |
| commissioner_district_hit_count | BIGINT        | YES    |       |           |         |
| library_district                | VARCHAR       | YES    |       |           |         |
| library_district_hit_count      | BIGINT        | YES    |       |           |         |
| library_service_area            | VARCHAR       | YES    |       |           |         |
| library_service_area_hit_count  | BIGINT        | YES    |       |           |         |

## r2://openskagit/derived/parcel_improvement_summary.parquet

| column_name                        | column_type   | null   | key   | default   | extra   |
|:-----------------------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number                      | VARCHAR       | YES    |       |           |         |
| improvement_building_count         | BIGINT        | YES    |       |           |         |
| improvement_detail_row_count       | DOUBLE        | YES    |       |           |         |
| improvement_segment_count          | DOUBLE        | YES    |       |           |         |
| total_improvement_value            | DOUBLE        | YES    |       |           |         |
| largest_building_improvement_value | DOUBLE        | YES    |       |           |         |
| total_living_area                  | DOUBLE        | YES    |       |           |         |
| largest_building_living_area       | DOUBLE        | YES    |       |           |         |
| oldest_actual_year_built           | INTEGER       | YES    |       |           |         |
| newest_actual_year_built           | INTEGER       | YES    |       |           |         |
| oldest_effective_year_built        | INTEGER       | YES    |       |           |         |
| newest_effective_year_built        | INTEGER       | YES    |       |           |         |
| total_main_area_calc_area          | DOUBLE        | YES    |       |           |         |
| total_garage_area                  | DOUBLE        | YES    |       |           |         |
| total_deck_area                    | DOUBLE        | YES    |       |           |         |
| improvement_descriptions           | VARCHAR       | YES    |       |           |         |
| building_styles                    | VARCHAR       | YES    |       |           |         |
| improvement_detail_types           | VARCHAR       | YES    |       |           |         |
| condition_codes                    | VARCHAR       | YES    |       |           |         |
| has_sketch                         | BOOLEAN       | YES    |       |           |         |
| primary_improvement_description    | VARCHAR       | YES    |       |           |         |
| primary_building_style             | VARCHAR       | YES    |       |           |         |
| improvement_comment                | VARCHAR       | YES    |       |           |         |
| primary_building_improvement_value | DOUBLE        | YES    |       |           |         |
| primary_building_living_area       | DOUBLE        | YES    |       |           |         |
| primary_actual_year_built          | INTEGER       | YES    |       |           |         |
| primary_effective_year_built       | INTEGER       | YES    |       |           |         |
| primary_building_age               | INTEGER       | YES    |       |           |         |
| primary_construction_style         | VARCHAR       | YES    |       |           |         |
| primary_foundation                 | VARCHAR       | YES    |       |           |         |
| primary_exterior_wall              | VARCHAR       | YES    |       |           |         |
| primary_roof_covering              | VARCHAR       | YES    |       |           |         |
| primary_roof_style                 | VARCHAR       | YES    |       |           |         |
| primary_heating_cooling            | VARCHAR       | YES    |       |           |         |
| primary_plumbing                   | VARCHAR       | YES    |       |           |         |
| primary_bedrooms_raw               | VARCHAR       | YES    |       |           |         |
| primary_sketchpath                 | VARCHAR       | YES    |       |           |         |

## r2://openskagit/derived/parcel_sales_summary.parquet

| column_name                               | column_type   | null   | key   | default   | extra   |
|:------------------------------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number                             | VARCHAR       | YES    |       |           |         |
| sale_record_count                         | BIGINT        | YES    |       |           |         |
| positive_price_sale_count                 | BIGINT        | YES    |       |           |         |
| valid_sale_count                          | BIGINT        | YES    |       |           |         |
| valid_warranty_sale_count                 | BIGINT        | YES    |       |           |         |
| first_deed_date                           | DATE          | YES    |       |           |         |
| last_deed_date                            | DATE          | YES    |       |           |         |
| last_transfer_deed_date                   | DATE          | YES    |       |           |         |
| last_transfer_price                       | DOUBLE        | YES    |       |           |         |
| last_transfer_type                        | VARCHAR       | YES    |       |           |         |
| last_transfer_deed_type                   | VARCHAR       | YES    |       |           |         |
| last_transfer_recording_number            | VARCHAR       | YES    |       |           |         |
| last_transfer_seller                      | VARCHAR       | YES    |       |           |         |
| last_transfer_buyer                       | VARCHAR       | YES    |       |           |         |
| last_valid_sale_date                      | DATE          | YES    |       |           |         |
| last_valid_sale_price                     | DOUBLE        | YES    |       |           |         |
| last_valid_sale_deed_type                 | VARCHAR       | YES    |       |           |         |
| last_valid_sale_recording_number          | VARCHAR       | YES    |       |           |         |
| last_valid_sale_seller                    | VARCHAR       | YES    |       |           |         |
| last_valid_sale_buyer                     | VARCHAR       | YES    |       |           |         |
| last_valid_warranty_sale_date             | DATE          | YES    |       |           |         |
| last_valid_warranty_sale_price            | DOUBLE        | YES    |       |           |         |
| last_valid_warranty_sale_recording_number | VARCHAR       | YES    |       |           |         |
| years_since_last_valid_sale               | BIGINT        | YES    |       |           |         |

## r2://openskagit/derived/parcel_search.parquet

| column_name                               | column_type   | null   | key   | default   | extra   |
|:------------------------------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number                             | VARCHAR       | YES    |       |           |         |
| aid                                       | BIGINT        | YES    |       |           |         |
| situs_address                             | VARCHAR       | YES    |       |           |         |
| situs_city_state_zip                      | VARCHAR       | YES    |       |           |         |
| owner_name                                | VARCHAR       | YES    |       |           |         |
| land_use                                  | VARCHAR       | YES    |       |           |         |
| acres                                     | DOUBLE        | YES    |       |           |         |
| assessor_year_built                       | INTEGER       | YES    |       |           |         |
| assessor_building_value                   | DOUBLE        | YES    |       |           |         |
| improved_land_value                       | DOUBLE        | YES    |       |           |         |
| assessed_value                            | DOUBLE        | YES    |       |           |         |
| has_situs_address                         | BOOLEAN       | YES    |       |           |         |
| gis_x                                     | DOUBLE        | YES    |       |           |         |
| gis_y                                     | DOUBLE        | YES    |       |           |         |
| has_geometry                              | BOOLEAN       | YES    |       |           |         |
| pnumber_record_count                      | BIGINT        | YES    |       |           |         |
| comp_plan_lud                             | VARCHAR       | YES    |       |           |         |
| zoning_code_short                         | VARCHAR       | YES    |       |           |         |
| zoning_label                              | VARCHAR       | YES    |       |           |         |
| zoning_code                               | VARCHAR       | YES    |       |           |         |
| comp_plan_hit_count                       | BIGINT        | YES    |       |           |         |
| city_name                                 | VARCHAR       | YES    |       |           |         |
| inside_city_limits                        | BOOLEAN       | YES    |       |           |         |
| city_hit_count                            | BIGINT        | YES    |       |           |         |
| fire_district                             | VARCHAR       | YES    |       |           |         |
| school_district_num                       | VARCHAR       | YES    |       |           |         |
| school_district_name                      | VARCHAR       | YES    |       |           |         |
| commissioner_district                     | VARCHAR       | YES    |       |           |         |
| commissioner_name                         | VARCHAR       | YES    |       |           |         |
| library_district                          | VARCHAR       | YES    |       |           |         |
| library_service_area                      | VARCHAR       | YES    |       |           |         |
| sale_record_count                         | BIGINT        | YES    |       |           |         |
| positive_price_sale_count                 | BIGINT        | YES    |       |           |         |
| valid_sale_count                          | BIGINT        | YES    |       |           |         |
| valid_warranty_sale_count                 | BIGINT        | YES    |       |           |         |
| first_deed_date                           | DATE          | YES    |       |           |         |
| last_deed_date                            | DATE          | YES    |       |           |         |
| last_transfer_deed_date                   | DATE          | YES    |       |           |         |
| last_transfer_price                       | DOUBLE        | YES    |       |           |         |
| last_transfer_type                        | VARCHAR       | YES    |       |           |         |
| last_transfer_deed_type                   | VARCHAR       | YES    |       |           |         |
| last_transfer_recording_number            | VARCHAR       | YES    |       |           |         |
| last_transfer_seller                      | VARCHAR       | YES    |       |           |         |
| last_transfer_buyer                       | VARCHAR       | YES    |       |           |         |
| last_valid_sale_date                      | DATE          | YES    |       |           |         |
| last_valid_sale_price                     | DOUBLE        | YES    |       |           |         |
| last_valid_sale_deed_type                 | VARCHAR       | YES    |       |           |         |
| last_valid_sale_recording_number          | VARCHAR       | YES    |       |           |         |
| last_valid_sale_seller                    | VARCHAR       | YES    |       |           |         |
| last_valid_sale_buyer                     | VARCHAR       | YES    |       |           |         |
| last_valid_warranty_sale_date             | DATE          | YES    |       |           |         |
| last_valid_warranty_sale_price            | DOUBLE        | YES    |       |           |         |
| last_valid_warranty_sale_recording_number | VARCHAR       | YES    |       |           |         |
| years_since_last_valid_sale               | BIGINT        | YES    |       |           |         |
| has_valid_sale                            | BOOLEAN       | YES    |       |           |         |
| sold_last_12_months                       | BOOLEAN       | YES    |       |           |         |
| sold_last_5_years                         | BOOLEAN       | YES    |       |           |         |
| improvement_building_count                | BIGINT        | YES    |       |           |         |
| improvement_detail_row_count              | DOUBLE        | YES    |       |           |         |
| improvement_segment_count                 | DOUBLE        | YES    |       |           |         |
| total_improvement_value                   | DOUBLE        | YES    |       |           |         |
| largest_building_improvement_value        | DOUBLE        | YES    |       |           |         |
| total_living_area                         | DOUBLE        | YES    |       |           |         |
| largest_building_living_area              | DOUBLE        | YES    |       |           |         |
| oldest_actual_year_built                  | INTEGER       | YES    |       |           |         |
| newest_actual_year_built                  | INTEGER       | YES    |       |           |         |
| oldest_effective_year_built               | INTEGER       | YES    |       |           |         |
| newest_effective_year_built               | INTEGER       | YES    |       |           |         |
| total_main_area_calc_area                 | DOUBLE        | YES    |       |           |         |
| total_garage_area                         | DOUBLE        | YES    |       |           |         |
| total_deck_area                           | DOUBLE        | YES    |       |           |         |
| improvement_descriptions                  | VARCHAR       | YES    |       |           |         |
| building_styles                           | VARCHAR       | YES    |       |           |         |
| improvement_detail_types                  | VARCHAR       | YES    |       |           |         |
| condition_codes                           | VARCHAR       | YES    |       |           |         |
| has_sketch                                | BOOLEAN       | YES    |       |           |         |
| primary_improvement_description           | VARCHAR       | YES    |       |           |         |
| primary_building_style                    | VARCHAR       | YES    |       |           |         |
| improvement_comment                       | VARCHAR       | YES    |       |           |         |
| primary_building_improvement_value        | DOUBLE        | YES    |       |           |         |
| primary_building_living_area              | DOUBLE        | YES    |       |           |         |
| primary_actual_year_built                 | INTEGER       | YES    |       |           |         |
| primary_effective_year_built              | INTEGER       | YES    |       |           |         |
| primary_building_age                      | INTEGER       | YES    |       |           |         |
| primary_construction_style                | VARCHAR       | YES    |       |           |         |
| primary_foundation                        | VARCHAR       | YES    |       |           |         |
| primary_exterior_wall                     | VARCHAR       | YES    |       |           |         |
| primary_roof_covering                     | VARCHAR       | YES    |       |           |         |
| primary_roof_style                        | VARCHAR       | YES    |       |           |         |
| primary_heating_cooling                   | VARCHAR       | YES    |       |           |         |
| primary_plumbing                          | VARCHAR       | YES    |       |           |         |
| primary_bedrooms_raw                      | VARCHAR       | YES    |       |           |         |
| primary_sketchpath                        | VARCHAR       | YES    |       |           |         |
| has_improvement_record                    | BOOLEAN       | YES    |       |           |         |

## r2://openskagit/derived/parcel_search_base.parquet

| column_name           | column_type   | null   | key   | default   | extra   |
|:----------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number         | VARCHAR       | YES    |       |           |         |
| aid                   | BIGINT        | YES    |       |           |         |
| situs_address         | VARCHAR       | YES    |       |           |         |
| situs_city_state_zip  | VARCHAR       | YES    |       |           |         |
| owner_name            | VARCHAR       | YES    |       |           |         |
| land_use              | VARCHAR       | YES    |       |           |         |
| acres                 | DOUBLE        | YES    |       |           |         |
| year_built            | INTEGER       | YES    |       |           |         |
| building_value        | DOUBLE        | YES    |       |           |         |
| improved_land_value   | DOUBLE        | YES    |       |           |         |
| assessed_value        | DOUBLE        | YES    |       |           |         |
| has_situs_address     | BOOLEAN       | YES    |       |           |         |
| gis_x                 | DOUBLE        | YES    |       |           |         |
| gis_y                 | DOUBLE        | YES    |       |           |         |
| has_geometry          | BOOLEAN       | YES    |       |           |         |
| pnumber_record_count  | BIGINT        | YES    |       |           |         |
| comp_plan_lud         | VARCHAR       | YES    |       |           |         |
| zoning_code_short     | VARCHAR       | YES    |       |           |         |
| zoning_label          | VARCHAR       | YES    |       |           |         |
| zoning_code           | VARCHAR       | YES    |       |           |         |
| comp_plan_hit_count   | BIGINT        | YES    |       |           |         |
| city_name             | VARCHAR       | YES    |       |           |         |
| inside_city_limits    | BOOLEAN       | YES    |       |           |         |
| city_hit_count        | BIGINT        | YES    |       |           |         |
| fire_district         | VARCHAR       | YES    |       |           |         |
| school_district_num   | VARCHAR       | YES    |       |           |         |
| school_district_name  | VARCHAR       | YES    |       |           |         |
| commissioner_district | VARCHAR       | YES    |       |           |         |
| commissioner_name     | VARCHAR       | YES    |       |           |         |
| library_district      | VARCHAR       | YES    |       |           |         |
| library_service_area  | VARCHAR       | YES    |       |           |         |

## r2://openskagit/derived/parcel_search_with_sales.parquet

| column_name                               | column_type   | null   | key   | default   | extra   |
|:------------------------------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number                             | VARCHAR       | YES    |       |           |         |
| aid                                       | BIGINT        | YES    |       |           |         |
| situs_address                             | VARCHAR       | YES    |       |           |         |
| situs_city_state_zip                      | VARCHAR       | YES    |       |           |         |
| owner_name                                | VARCHAR       | YES    |       |           |         |
| land_use                                  | VARCHAR       | YES    |       |           |         |
| acres                                     | DOUBLE        | YES    |       |           |         |
| year_built                                | INTEGER       | YES    |       |           |         |
| building_value                            | DOUBLE        | YES    |       |           |         |
| improved_land_value                       | DOUBLE        | YES    |       |           |         |
| assessed_value                            | DOUBLE        | YES    |       |           |         |
| has_situs_address                         | BOOLEAN       | YES    |       |           |         |
| gis_x                                     | DOUBLE        | YES    |       |           |         |
| gis_y                                     | DOUBLE        | YES    |       |           |         |
| has_geometry                              | BOOLEAN       | YES    |       |           |         |
| pnumber_record_count                      | BIGINT        | YES    |       |           |         |
| comp_plan_lud                             | VARCHAR       | YES    |       |           |         |
| zoning_code_short                         | VARCHAR       | YES    |       |           |         |
| zoning_label                              | VARCHAR       | YES    |       |           |         |
| zoning_code                               | VARCHAR       | YES    |       |           |         |
| comp_plan_hit_count                       | BIGINT        | YES    |       |           |         |
| city_name                                 | VARCHAR       | YES    |       |           |         |
| inside_city_limits                        | BOOLEAN       | YES    |       |           |         |
| city_hit_count                            | BIGINT        | YES    |       |           |         |
| fire_district                             | VARCHAR       | YES    |       |           |         |
| school_district_num                       | VARCHAR       | YES    |       |           |         |
| school_district_name                      | VARCHAR       | YES    |       |           |         |
| commissioner_district                     | VARCHAR       | YES    |       |           |         |
| commissioner_name                         | VARCHAR       | YES    |       |           |         |
| library_district                          | VARCHAR       | YES    |       |           |         |
| library_service_area                      | VARCHAR       | YES    |       |           |         |
| sale_record_count                         | BIGINT        | YES    |       |           |         |
| positive_price_sale_count                 | BIGINT        | YES    |       |           |         |
| valid_sale_count                          | BIGINT        | YES    |       |           |         |
| valid_warranty_sale_count                 | BIGINT        | YES    |       |           |         |
| first_deed_date                           | DATE          | YES    |       |           |         |
| last_deed_date                            | DATE          | YES    |       |           |         |
| last_transfer_deed_date                   | DATE          | YES    |       |           |         |
| last_transfer_price                       | DOUBLE        | YES    |       |           |         |
| last_transfer_type                        | VARCHAR       | YES    |       |           |         |
| last_transfer_deed_type                   | VARCHAR       | YES    |       |           |         |
| last_transfer_recording_number            | VARCHAR       | YES    |       |           |         |
| last_transfer_seller                      | VARCHAR       | YES    |       |           |         |
| last_transfer_buyer                       | VARCHAR       | YES    |       |           |         |
| last_valid_sale_date                      | DATE          | YES    |       |           |         |
| last_valid_sale_price                     | DOUBLE        | YES    |       |           |         |
| last_valid_sale_deed_type                 | VARCHAR       | YES    |       |           |         |
| last_valid_sale_recording_number          | VARCHAR       | YES    |       |           |         |
| last_valid_sale_seller                    | VARCHAR       | YES    |       |           |         |
| last_valid_sale_buyer                     | VARCHAR       | YES    |       |           |         |
| last_valid_warranty_sale_date             | DATE          | YES    |       |           |         |
| last_valid_warranty_sale_price            | DOUBLE        | YES    |       |           |         |
| last_valid_warranty_sale_recording_number | VARCHAR       | YES    |       |           |         |
| years_since_last_valid_sale               | BIGINT        | YES    |       |           |         |
| has_valid_sale                            | BOOLEAN       | YES    |       |           |         |
| sold_last_12_months                       | BOOLEAN       | YES    |       |           |         |
| sold_last_5_years                         | BOOLEAN       | YES    |       |           |         |

## r2://openskagit/derived/parcel_search_with_sales_improvements.parquet

| column_name                               | column_type   | null   | key   | default   | extra   |
|:------------------------------------------|:--------------|:-------|:------|:----------|:--------|
| parcel_number                             | VARCHAR       | YES    |       |           |         |
| aid                                       | BIGINT        | YES    |       |           |         |
| situs_address                             | VARCHAR       | YES    |       |           |         |
| situs_city_state_zip                      | VARCHAR       | YES    |       |           |         |
| owner_name                                | VARCHAR       | YES    |       |           |         |
| land_use                                  | VARCHAR       | YES    |       |           |         |
| acres                                     | DOUBLE        | YES    |       |           |         |
| year_built                                | INTEGER       | YES    |       |           |         |
| building_value                            | DOUBLE        | YES    |       |           |         |
| improved_land_value                       | DOUBLE        | YES    |       |           |         |
| assessed_value                            | DOUBLE        | YES    |       |           |         |
| has_situs_address                         | BOOLEAN       | YES    |       |           |         |
| gis_x                                     | DOUBLE        | YES    |       |           |         |
| gis_y                                     | DOUBLE        | YES    |       |           |         |
| has_geometry                              | BOOLEAN       | YES    |       |           |         |
| pnumber_record_count                      | BIGINT        | YES    |       |           |         |
| comp_plan_lud                             | VARCHAR       | YES    |       |           |         |
| zoning_code_short                         | VARCHAR       | YES    |       |           |         |
| zoning_label                              | VARCHAR       | YES    |       |           |         |
| zoning_code                               | VARCHAR       | YES    |       |           |         |
| comp_plan_hit_count                       | BIGINT        | YES    |       |           |         |
| city_name                                 | VARCHAR       | YES    |       |           |         |
| inside_city_limits                        | BOOLEAN       | YES    |       |           |         |
| city_hit_count                            | BIGINT        | YES    |       |           |         |
| fire_district                             | VARCHAR       | YES    |       |           |         |
| school_district_num                       | VARCHAR       | YES    |       |           |         |
| school_district_name                      | VARCHAR       | YES    |       |           |         |
| commissioner_district                     | VARCHAR       | YES    |       |           |         |
| commissioner_name                         | VARCHAR       | YES    |       |           |         |
| library_district                          | VARCHAR       | YES    |       |           |         |
| library_service_area                      | VARCHAR       | YES    |       |           |         |
| sale_record_count                         | BIGINT        | YES    |       |           |         |
| positive_price_sale_count                 | BIGINT        | YES    |       |           |         |
| valid_sale_count                          | BIGINT        | YES    |       |           |         |
| valid_warranty_sale_count                 | BIGINT        | YES    |       |           |         |
| first_deed_date                           | DATE          | YES    |       |           |         |
| last_deed_date                            | DATE          | YES    |       |           |         |
| last_transfer_deed_date                   | DATE          | YES    |       |           |         |
| last_transfer_price                       | DOUBLE        | YES    |       |           |         |
| last_transfer_type                        | VARCHAR       | YES    |       |           |         |
| last_transfer_deed_type                   | VARCHAR       | YES    |       |           |         |
| last_transfer_recording_number            | VARCHAR       | YES    |       |           |         |
| last_transfer_seller                      | VARCHAR       | YES    |       |           |         |
| last_transfer_buyer                       | VARCHAR       | YES    |       |           |         |
| last_valid_sale_date                      | DATE          | YES    |       |           |         |
| last_valid_sale_price                     | DOUBLE        | YES    |       |           |         |
| last_valid_sale_deed_type                 | VARCHAR       | YES    |       |           |         |
| last_valid_sale_recording_number          | VARCHAR       | YES    |       |           |         |
| last_valid_sale_seller                    | VARCHAR       | YES    |       |           |         |
| last_valid_sale_buyer                     | VARCHAR       | YES    |       |           |         |
| last_valid_warranty_sale_date             | DATE          | YES    |       |           |         |
| last_valid_warranty_sale_price            | DOUBLE        | YES    |       |           |         |
| last_valid_warranty_sale_recording_number | VARCHAR       | YES    |       |           |         |
| years_since_last_valid_sale               | BIGINT        | YES    |       |           |         |
| has_valid_sale                            | BOOLEAN       | YES    |       |           |         |
| sold_last_12_months                       | BOOLEAN       | YES    |       |           |         |
| sold_last_5_years                         | BOOLEAN       | YES    |       |           |         |
| improvement_building_count                | BIGINT        | YES    |       |           |         |
| improvement_detail_row_count              | DOUBLE        | YES    |       |           |         |
| improvement_segment_count                 | DOUBLE        | YES    |       |           |         |
| total_improvement_value                   | DOUBLE        | YES    |       |           |         |
| largest_building_improvement_value        | DOUBLE        | YES    |       |           |         |
| total_living_area                         | DOUBLE        | YES    |       |           |         |
| largest_building_living_area              | DOUBLE        | YES    |       |           |         |
| oldest_actual_year_built                  | INTEGER       | YES    |       |           |         |
| newest_actual_year_built                  | INTEGER       | YES    |       |           |         |
| oldest_effective_year_built               | INTEGER       | YES    |       |           |         |
| newest_effective_year_built               | INTEGER       | YES    |       |           |         |
| total_main_area_calc_area                 | DOUBLE        | YES    |       |           |         |
| total_garage_area                         | DOUBLE        | YES    |       |           |         |
| total_deck_area                           | DOUBLE        | YES    |       |           |         |
| improvement_descriptions                  | VARCHAR       | YES    |       |           |         |
| building_styles                           | VARCHAR       | YES    |       |           |         |
| improvement_detail_types                  | VARCHAR       | YES    |       |           |         |
| condition_codes                           | VARCHAR       | YES    |       |           |         |
| has_sketch                                | BOOLEAN       | YES    |       |           |         |
| primary_improvement_description           | VARCHAR       | YES    |       |           |         |
| primary_building_style                    | VARCHAR       | YES    |       |           |         |
| improvement_comment                       | VARCHAR       | YES    |       |           |         |
| primary_building_improvement_value        | DOUBLE        | YES    |       |           |         |
| primary_building_living_area              | DOUBLE        | YES    |       |           |         |
| primary_actual_year_built                 | INTEGER       | YES    |       |           |         |
| primary_effective_year_built              | INTEGER       | YES    |       |           |         |
| primary_building_age                      | INTEGER       | YES    |       |           |         |
| primary_construction_style                | VARCHAR       | YES    |       |           |         |
| primary_foundation                        | VARCHAR       | YES    |       |           |         |
| primary_exterior_wall                     | VARCHAR       | YES    |       |           |         |
| primary_roof_covering                     | VARCHAR       | YES    |       |           |         |
| primary_roof_style                        | VARCHAR       | YES    |       |           |         |
| primary_heating_cooling                   | VARCHAR       | YES    |       |           |         |
| primary_plumbing                          | VARCHAR       | YES    |       |           |         |
| primary_bedrooms_raw                      | VARCHAR       | YES    |       |           |         |
| primary_sketchpath                        | VARCHAR       | YES    |       |           |         |
| has_improvement_record                    | BOOLEAN       | YES    |       |           |         |

## r2://openskagit/geoparquet/AddressRanges.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| Shape_Leng    | DOUBLE        | YES    |       |           |         |
| Sys_Id        | BIGINT        | YES    |       |           |         |
| Road_No       | VARCHAR       | YES    |       |           |         |
| PreDir        | VARCHAR       | YES    |       |           |         |
| PreType       | VARCHAR       | YES    |       |           |         |
| StreetName    | VARCHAR       | YES    |       |           |         |
| StreetType    | VARCHAR       | YES    |       |           |         |
| SufDir        | VARCHAR       | YES    |       |           |         |
| FromLeft      | VARCHAR       | YES    |       |           |         |
| ToLeft        | VARCHAR       | YES    |       |           |         |
| FromRight     | VARCHAR       | YES    |       |           |         |
| ToRight       | VARCHAR       | YES    |       |           |         |
| Side          | VARCHAR       | YES    |       |           |         |
| LeftZip       | VARCHAR       | YES    |       |           |         |
| RightZip      | VARCHAR       | YES    |       |           |         |
| L_AddAuth     | VARCHAR       | YES    |       |           |         |
| R_AddAuth     | VARCHAR       | YES    |       |           |         |
| L_LocZn       | VARCHAR       | YES    |       |           |         |
| R_LocZn       | VARCHAR       | YES    |       |           |         |
| Alias1        | VARCHAR       | YES    |       |           |         |
| Alias2        | VARCHAR       | YES    |       |           |         |
| Alias3        | VARCHAR       | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/LibraryDistricts.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| LIB_DIST_N    | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/LibraryServiceAreas.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| LIB_SVC_AR    | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/PNumbers.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| PNUMBERID     | BIGINT        | YES    |       |           |         |
| PNUMBER       | VARCHAR       | YES    |       |           |         |
| ENTITYHAND    | VARCHAR       | YES    |       |           |         |
| XCOORDINAT    | DOUBLE        | YES    |       |           |         |
| YCOORDINAT    | DOUBLE        | YES    |       |           |         |
| ZCOORDINAT    | DOUBLE        | YES    |       |           |         |
| DRAWINGNAM    | VARCHAR       | YES    |       |           |         |
| ROTATION      | DOUBLE        | YES    |       |           |         |
| SCALE         | BIGINT        | YES    |       |           |         |
| INTEREST      | BIGINT        | YES    |       |           |         |
| ACCOUNTTYP    | BIGINT        | YES    |       |           |         |
| PARENTPROP    | INTEGER       | YES    |       |           |         |
| MODDATE       | TIMESTAMP     | YES    |       |           |         |
| MODUSER       | VARCHAR       | YES    |       |           |         |
| VERIFIED      | BIGINT        | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/PublicPlaces.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| NAME          | VARCHAR       | YES    |       |           |         |
| LOCATION      | VARCHAR       | YES    |       |           |         |
| ADDRESSNUM    | VARCHAR       | YES    |       |           |         |
| ADDRESSSTR    | VARCHAR       | YES    |       |           |         |
| ADDRESSCIT    | VARCHAR       | YES    |       |           |         |
| NOTES         | VARCHAR       | YES    |       |           |         |
| IMAGENAME     | VARCHAR       | YES    |       |           |         |
| TYPE          | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/TideGates.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| TYPE          | VARCHAR       | YES    |       |           |         |
| CLASS         | VARCHAR       | YES    |       |           |         |
| CONTROL_ID    | INTEGER       | YES    |       |           |         |
| TYPE_CODE     | VARCHAR       | YES    |       |           |         |
| DISTRICT      | VARCHAR       | YES    |       |           |         |
| NAME          | VARCHAR       | YES    |       |           |         |
| TUBESDESC     | VARCHAR       | YES    |       |           |         |
| PIPETYPE      | VARCHAR       | YES    |       |           |         |
| LID           | VARCHAR       | YES    |       |           |         |
| INSTALLED     | VARCHAR       | YES    |       |           |         |
| ELEVATION     | INTEGER       | YES    |       |           |         |
| MAINTENANC    | VARCHAR       | YES    |       |           |         |
| LAT           | DOUBLE        | YES    |       |           |         |
| LONGITUDE     | DOUBLE        | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/citylimits.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| NAME          | VARCHAR       | YES    |       |           |         |
| CITY          | INTEGER       | YES    |       |           |         |
| ACRES         | DOUBLE        | YES    |       |           |         |
| scgis_SDEA    | DOUBLE        | YES    |       |           |         |
| scgis_SD_1    | DOUBLE        | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/commissionerdistricts.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| COMMDIST      | INTEGER       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| COMNAME       | VARCHAR       | YES    |       |           |         |
| PHOTO         | VARCHAR       | YES    |       |           |         |
| WEBSITE       | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/compplan.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| ACRES         | DOUBLE        | YES    |       |           |         |
| FEDERAL       | VARCHAR       | YES    |       |           |         |
| FEAT_TYPE     | VARCHAR       | YES    |       |           |         |
| LUD           | VARCHAR       | YES    |       |           |         |
| LUD_ZONING    | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| ZONING_LAB    | VARCHAR       | YES    |       |           |         |
| ZONING_COD    | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/firedistricts.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| DISTRICT      | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/historical.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| OBJECTID      | BIGINT        | YES    |       |           |         |
| Type          | INTEGER       | YES    |       |           |         |
| Name          | VARCHAR       | YES    |       |           |         |
| FileName      | VARCHAR       | YES    |       |           |         |
| HistoryID     | BIGINT        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/roads-all.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| ROAD_NO       | VARCHAR       | YES    |       |           |         |
| TYPE          | VARCHAR       | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/roads-named.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| ROAD_NO       | VARCHAR       | YES    |       |           |         |
| ROAD_NM       | VARCHAR       | YES    |       |           |         |
| ROAD_DES      | VARCHAR       | YES    |       |           |         |
| TYPE          | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/geoparquet/schooldistricts.parquet

| column_name   | column_type   | null   | key   | default   | extra   |
|:--------------|:--------------|:-------|:------|:----------|:--------|
| DIST_NUM      | INTEGER       | YES    |       |           |         |
| NAME          | VARCHAR       | YES    |       |           |         |
| COUNTY        | VARCHAR       | YES    |       |           |         |
| GlobalID      | VARCHAR       | YES    |       |           |         |
| Shape_STAr    | DOUBLE        | YES    |       |           |         |
| Shape_STLe    | DOUBLE        | YES    |       |           |         |
| geometry      | BLOB          | YES    |       |           |         |

## r2://openskagit/improvements.parquet

| column_name        | column_type   | null   | key   | default   | extra   |
|:-------------------|:--------------|:-------|:------|:----------|:--------|
| ParcelNumber       | VARCHAR       | YES    |       |           |         |
| imprv_id           | VARCHAR       | YES    |       |           |         |
| description        | VARCHAR       | YES    |       |           |         |
| building_style     | VARCHAR       | YES    |       |           |         |
| comment            | VARCHAR       | YES    |       |           |         |
| imprv_val          | VARCHAR       | YES    |       |           |         |
| new_const_year     | VARCHAR       | YES    |       |           |         |
| tot_living_area    | VARCHAR       | YES    |       |           |         |
| segment_id         | VARCHAR       | YES    |       |           |         |
| imprv_det_type_cd  | VARCHAR       | YES    |       |           |         |
| imprv_det_class_cd | VARCHAR       | YES    |       |           |         |
| imprv_det_meth_cd  | VARCHAR       | YES    |       |           |         |
| condition_cd       | VARCHAR       | YES    |       |           |         |
| calc_area          | VARCHAR       | YES    |       |           |         |
| unit_price         | VARCHAR       | YES    |       |           |         |
| dep_pct            | VARCHAR       | YES    |       |           |         |
| imprv_det_val      | VARCHAR       | YES    |       |           |         |
| ConstructionStyle  | VARCHAR       | YES    |       |           |         |
| Foundation         | VARCHAR       | YES    |       |           |         |
| ExteriorWall       | VARCHAR       | YES    |       |           |         |
| RoofCovering       | VARCHAR       | YES    |       |           |         |
| RoofStyle          | VARCHAR       | YES    |       |           |         |
| Flooring           | VARCHAR       | YES    |       |           |         |
| FloorConstruction  | VARCHAR       | YES    |       |           |         |
| InteriorFinish     | VARCHAR       | YES    |       |           |         |
| Plumbing           | VARCHAR       | YES    |       |           |         |
| Appliances         | VARCHAR       | YES    |       |           |         |
| HeatingCooling     | VARCHAR       | YES    |       |           |         |
| Fireplace          | VARCHAR       | YES    |       |           |         |
| Rooms              | VARCHAR       | YES    |       |           |         |
| Bedrooms           | VARCHAR       | YES    |       |           |         |
| effective_yr_blt   | VARCHAR       | YES    |       |           |         |
| actual_year_built  | VARCHAR       | YES    |       |           |         |
| sketchpath         | VARCHAR       | YES    |       |           |         |

## r2://openskagit/land.parquet

| column_name              | column_type   | null   | key   | default   | extra   |
|:-------------------------|:--------------|:-------|:------|:----------|:--------|
| ParcelNumber             | VARCHAR       | YES    |       |           |         |
| prop_val_yr              | VARCHAR       | YES    |       |           |         |
| land_seg_id              | VARCHAR       | YES    |       |           |         |
| land_type                | VARCHAR       | YES    |       |           |         |
| appr_meth                | VARCHAR       | YES    |       |           |         |
| size_acres               | VARCHAR       | YES    |       |           |         |
| size_square_feet         | VARCHAR       | YES    |       |           |         |
| effective_front          | VARCHAR       | YES    |       |           |         |
| actual_front             | VARCHAR       | YES    |       |           |         |
| land_adj_factor          | VARCHAR       | YES    |       |           |         |
| adj_value                | VARCHAR       | YES    |       |           |         |
| mkt_unit_price           | VARCHAR       | YES    |       |           |         |
| market_value             | VARCHAR       | YES    |       |           |         |
| open_space_val           | VARCHAR       | YES    |       |           |         |
| open_space_use_code_desc | VARCHAR       | YES    |       |           |         |
| ag_unit_price            | VARCHAR       | YES    |       |           |         |
| os_appr_meth             | VARCHAR       | YES    |       |           |         |
| land_seg_comment         | VARCHAR       | YES    |       |           |         |

## r2://openskagit/sales.parquet

| column_name      | column_type   | null   | key   | default   | extra   |
|:-----------------|:--------------|:-------|:------|:----------|:--------|
| SaleID           | VARCHAR       | YES    |       |           |         |
| Parcel Number    | VARCHAR       | YES    |       |           |         |
| Account Number   | VARCHAR       | YES    |       |           |         |
| seller name      | VARCHAR       | YES    |       |           |         |
| buyer name       | VARCHAR       | YES    |       |           |         |
| sale price       | VARCHAR       | YES    |       |           |         |
| sale date        | VARCHAR       | YES    |       |           |         |
| sale type        | VARCHAR       | YES    |       |           |         |
| Recording Number | VARCHAR       | YES    |       |           |         |
| Deed Type        | VARCHAR       | YES    |       |           |         |
| deed date        | VARCHAR       | YES    |       |           |         |
| reval area       | VARCHAR       | YES    |       |           |         |
| Excise Number    | VARCHAR       | YES    |       |           |         |

