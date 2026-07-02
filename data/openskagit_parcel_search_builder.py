"""
openskagit_parcel_search_builder.py

Clean builder for OpenSkagit / ParcelBook parcel search data.

Final output:
    r2://openskagit/derived/parcel_search.parquet

Helper outputs:
    r2://openskagit/derived/parcel_geo_flags.parquet
    r2://openskagit/derived/parcel_sales_summary.parquet
    r2://openskagit/derived/parcel_improvement_summary.parquet

Colab usage:

    !pip install duckdb pandas -q

    from openskagit_parcel_search_builder import OpenSkagitParcelSearchBuilder

    builder = OpenSkagitParcelSearchBuilder(
        bucket="openskagit",
        account_id="YOUR_R2_ACCOUNT_ID",
        key_id="YOUR_R2_KEY_ID",
        secret="YOUR_R2_SECRET",
    )

    results = builder.run_all()

    # or run individual stages:
    builder.connect()
    builder.build_improvement_summary()
    builder.build_parcel_search()
    builder.validate_all()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import duckdb
import pandas as pd


@dataclass
class OpenSkagitParcelSearchBuilder:
    bucket: str
    account_id: str
    key_id: str
    secret: str
    con: Optional[duckdb.DuckDBPyConnection] = None

    def __post_init__(self) -> None:
        if self.con is None:
            self.con = duckdb.connect()

    @property
    def r2(self) -> str:
        return f"r2://{self.bucket}"

    def connect(self) -> None:
        self.con.execute("INSTALL httpfs;")
        self.con.execute("LOAD httpfs;")
        self.con.execute("INSTALL spatial;")
        self.con.execute("LOAD spatial;")
        self.con.execute(f"""
        CREATE OR REPLACE SECRET r2_secret (
            TYPE R2,
            KEY_ID '{self.key_id}',
            SECRET '{self.secret}',
            ACCOUNT_ID '{self.account_id}'
        );
        """)

    def build_geo_flags(self) -> None:
        self.con.execute(f"""
        COPY (
            WITH assessor AS (
                SELECT DISTINCT upper(trim("Parcel Number")) AS parcel_number
                FROM read_parquet('{self.r2}/assessor.parquet')
                WHERE "Parcel Number" IS NOT NULL
            ),
            pnums AS (
                SELECT
                    upper(trim(PNUMBER)) AS parcel_number,
                    ANY_VALUE(XCOORDINAT) AS gis_x,
                    ANY_VALUE(YCOORDINAT) AS gis_y,
                    ANY_VALUE(geometry) AS parcel_geom,
                    COUNT(*) AS pnumber_record_count
                FROM read_parquet('{self.r2}/geoparquet/PNumbers.parquet')
                WHERE PNUMBER IS NOT NULL
                GROUP BY upper(trim(PNUMBER))
            ),
            compplan_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS comp_plan_hit_count,
                    string_agg(DISTINCT cp.LUD, ' | ') AS comp_plan_lud,
                    string_agg(DISTINCT cp.LUD_ZONING, ' | ') AS zoning_code_short,
                    string_agg(DISTINCT cp.ZONING_LAB, ' | ') AS zoning_label,
                    string_agg(DISTINCT cp.ZONING_COD, ' | ') AS zoning_code
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/compplan.parquet') cp
                    ON ST_Within(p.parcel_geom, cp.geometry)
                GROUP BY p.parcel_number
            ),
            city_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS city_hit_count,
                    string_agg(DISTINCT cl.NAME, ' | ') AS city_name
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/citylimits.parquet') cl
                    ON ST_Within(p.parcel_geom, cl.geometry)
                GROUP BY p.parcel_number
            ),
            fire_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS fire_district_hit_count,
                    string_agg(DISTINCT fd.DISTRICT, ' | ') AS fire_district
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/firedistricts.parquet') fd
                    ON ST_Within(p.parcel_geom, fd.geometry)
                GROUP BY p.parcel_number
            ),
            school_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS school_district_hit_count,
                    string_agg(DISTINCT CAST(sd.DIST_NUM AS VARCHAR), ' | ') AS school_district_num,
                    string_agg(DISTINCT sd.NAME, ' | ') AS school_district_name
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/schooldistricts.parquet') sd
                    ON ST_Within(p.parcel_geom, sd.geometry)
                GROUP BY p.parcel_number
            ),
            commissioner_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS commissioner_district_hit_count,
                    string_agg(DISTINCT CAST(cd.COMMDIST AS VARCHAR), ' | ') AS commissioner_district,
                    string_agg(DISTINCT cd.COMNAME, ' | ') AS commissioner_name
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/commissionerdistricts.parquet') cd
                    ON ST_Within(p.parcel_geom, cd.geometry)
                GROUP BY p.parcel_number
            ),
            library_district_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS library_district_hit_count,
                    string_agg(DISTINCT ld.LIB_DIST_N, ' | ') AS library_district
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/LibraryDistricts.parquet') ld
                    ON ST_Within(p.parcel_geom, ld.geometry)
                GROUP BY p.parcel_number
            ),
            library_service_flags AS (
                SELECT
                    p.parcel_number,
                    COUNT(*) AS library_service_area_hit_count,
                    string_agg(DISTINCT lsa.LIB_SVC_AR, ' | ') AS library_service_area
                FROM pnums p
                JOIN read_parquet('{self.r2}/geoparquet/LibraryServiceAreas.parquet') lsa
                    ON ST_Within(p.parcel_geom, lsa.geometry)
                GROUP BY p.parcel_number
            )
            SELECT
                a.parcel_number,
                p.gis_x,
                p.gis_y,
                CASE WHEN p.parcel_geom IS NOT NULL THEN TRUE ELSE FALSE END AS has_geometry,
                COALESCE(p.pnumber_record_count, 0) AS pnumber_record_count,
                cf.comp_plan_lud,
                cf.zoning_code_short,
                cf.zoning_label,
                cf.zoning_code,
                COALESCE(cf.comp_plan_hit_count, 0) AS comp_plan_hit_count,
                city.city_name,
                CASE WHEN city.city_name IS NOT NULL THEN TRUE ELSE FALSE END AS inside_city_limits,
                COALESCE(city.city_hit_count, 0) AS city_hit_count,
                fire.fire_district,
                COALESCE(fire.fire_district_hit_count, 0) AS fire_district_hit_count,
                school.school_district_num,
                school.school_district_name,
                COALESCE(school.school_district_hit_count, 0) AS school_district_hit_count,
                comm.commissioner_district,
                comm.commissioner_name,
                COALESCE(comm.commissioner_district_hit_count, 0) AS commissioner_district_hit_count,
                lib.library_district,
                COALESCE(lib.library_district_hit_count, 0) AS library_district_hit_count,
                lsa.library_service_area,
                COALESCE(lsa.library_service_area_hit_count, 0) AS library_service_area_hit_count
            FROM assessor a
            LEFT JOIN pnums p USING (parcel_number)
            LEFT JOIN compplan_flags cf USING (parcel_number)
            LEFT JOIN city_flags city USING (parcel_number)
            LEFT JOIN fire_flags fire USING (parcel_number)
            LEFT JOIN school_flags school USING (parcel_number)
            LEFT JOIN commissioner_flags comm USING (parcel_number)
            LEFT JOIN library_district_flags lib USING (parcel_number)
            LEFT JOIN library_service_flags lsa USING (parcel_number)
        )
        TO '{self.r2}/derived/parcel_geo_flags.parquet'
        (FORMAT PARQUET);
        """)

    def build_sales_summary(self) -> None:
        self.con.execute(f"""
        COPY (
            WITH sales_clean AS (
                SELECT
                    upper(trim("Parcel Number")) AS parcel_number,
                    TRY_CAST(SaleID AS BIGINT) AS sale_id,
                    NULLIF(trim("seller name"), '') AS seller_name,
                    NULLIF(trim("buyer name"), '') AS buyer_name,
                    TRY_CAST(regexp_replace("sale price", '[^0-9.-]', '', 'g') AS DOUBLE) AS sale_price,
                    TRY_CAST("sale date" AS TIMESTAMP)::DATE AS raw_sale_date,
                    TRY_CAST("deed date" AS TIMESTAMP)::DATE AS deed_date,
                    upper(trim("sale type")) AS sale_type,
                    NULLIF(trim("Recording Number"), '') AS recording_number,
                    upper(trim("Deed Type")) AS deed_type,
                    NULLIF(trim("Excise Number"), '') AS excise_number
                FROM read_parquet('{self.r2}/sales.parquet')
                WHERE "Parcel Number" IS NOT NULL
            ),
            sales_scored AS (
                SELECT
                    *,
                    CASE WHEN sale_price > 0 THEN TRUE ELSE FALSE END AS is_positive_price,
                    CASE
                        WHEN sale_type = 'VALID SALE' AND sale_price > 0 AND deed_date IS NOT NULL
                        THEN TRUE ELSE FALSE
                    END AS is_valid_sale,
                    CASE
                        WHEN sale_type = 'VALID SALE'
                             AND deed_type = 'WARRANTY DEED'
                             AND sale_price > 0
                             AND deed_date IS NOT NULL
                        THEN TRUE ELSE FALSE
                    END AS is_valid_warranty_sale
                FROM sales_clean
            ),
            latest_any AS (
                SELECT * FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY parcel_number
                        ORDER BY deed_date DESC NULLS LAST, sale_id DESC NULLS LAST
                    ) AS rn
                    FROM sales_scored
                ) WHERE rn = 1
            ),
            latest_valid AS (
                SELECT * FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY parcel_number
                        ORDER BY deed_date DESC NULLS LAST, sale_id DESC NULLS LAST
                    ) AS rn
                    FROM sales_scored
                    WHERE is_valid_sale = TRUE
                ) WHERE rn = 1
            ),
            latest_valid_warranty AS (
                SELECT * FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY parcel_number
                        ORDER BY deed_date DESC NULLS LAST, sale_id DESC NULLS LAST
                    ) AS rn
                    FROM sales_scored
                    WHERE is_valid_warranty_sale = TRUE
                ) WHERE rn = 1
            ),
            sales_counts AS (
                SELECT
                    parcel_number,
                    COUNT(*) AS sale_record_count,
                    COUNT(*) FILTER (WHERE is_positive_price = TRUE) AS positive_price_sale_count,
                    COUNT(*) FILTER (WHERE is_valid_sale = TRUE) AS valid_sale_count,
                    COUNT(*) FILTER (WHERE is_valid_warranty_sale = TRUE) AS valid_warranty_sale_count,
                    MIN(deed_date) AS first_deed_date,
                    MAX(deed_date) AS last_deed_date
                FROM sales_scored
                GROUP BY parcel_number
            )
            SELECT
                c.parcel_number,
                c.sale_record_count,
                c.positive_price_sale_count,
                c.valid_sale_count,
                c.valid_warranty_sale_count,
                c.first_deed_date,
                c.last_deed_date,
                la.deed_date AS last_transfer_deed_date,
                la.sale_price AS last_transfer_price,
                la.sale_type AS last_transfer_type,
                la.deed_type AS last_transfer_deed_type,
                la.recording_number AS last_transfer_recording_number,
                la.seller_name AS last_transfer_seller,
                la.buyer_name AS last_transfer_buyer,
                lv.deed_date AS last_valid_sale_date,
                lv.sale_price AS last_valid_sale_price,
                lv.deed_type AS last_valid_sale_deed_type,
                lv.recording_number AS last_valid_sale_recording_number,
                lv.seller_name AS last_valid_sale_seller,
                lv.buyer_name AS last_valid_sale_buyer,
                lvw.deed_date AS last_valid_warranty_sale_date,
                lvw.sale_price AS last_valid_warranty_sale_price,
                lvw.recording_number AS last_valid_warranty_sale_recording_number,
                date_diff('year', lv.deed_date, current_date) AS years_since_last_valid_sale
            FROM sales_counts c
            LEFT JOIN latest_any la USING (parcel_number)
            LEFT JOIN latest_valid lv USING (parcel_number)
            LEFT JOIN latest_valid_warranty lvw USING (parcel_number)
        )
        TO '{self.r2}/derived/parcel_sales_summary.parquet'
        (FORMAT PARQUET);
        """)

    def build_improvement_summary(self) -> None:
        self.con.execute(f"""
        COPY (
            WITH raw_pre AS (
                SELECT
                    upper(trim(ParcelNumber)) AS parcel_number,
                    TRY_CAST(imprv_id AS BIGINT) AS imprv_id,
                    TRY_CAST(segment_id AS BIGINT) AS segment_id,
                    NULLIF(trim(description), '') AS description,
                    NULLIF(trim(building_style), '') AS building_style,
                    NULLIF(trim(comment), '') AS comment,
                    TRY_CAST(regexp_replace(imprv_val, '[^0-9.-]', '', 'g') AS DOUBLE) AS imprv_val,
                    TRY_CAST(regexp_replace(tot_living_area, '[^0-9.-]', '', 'g') AS DOUBLE) AS tot_living_area,
                    TRY_CAST(regexp_replace(calc_area, '[^0-9.-]', '', 'g') AS DOUBLE) AS calc_area,
                    TRY_CAST(regexp_replace(new_const_year, '[^0-9]', '', 'g') AS INTEGER) AS new_const_year_raw,
                    TRY_CAST(regexp_replace(effective_yr_blt, '[^0-9]', '', 'g') AS INTEGER) AS effective_yr_blt_raw,
                    TRY_CAST(regexp_replace(actual_year_built, '[^0-9]', '', 'g') AS INTEGER) AS actual_year_built_raw,
                    upper(trim(imprv_det_type_cd)) AS imprv_det_type_cd,
                    upper(trim(condition_cd)) AS condition_cd,
                    NULLIF(trim(ConstructionStyle), '') AS construction_style,
                    NULLIF(trim(Foundation), '') AS foundation,
                    NULLIF(trim(ExteriorWall), '') AS exterior_wall,
                    NULLIF(trim(RoofCovering), '') AS roof_covering,
                    NULLIF(trim(RoofStyle), '') AS roof_style,
                    NULLIF(trim(HeatingCooling), '') AS heating_cooling,
                    NULLIF(trim(Plumbing), '') AS plumbing,
                    NULLIF(trim(Bedrooms), '') AS bedrooms_raw,
                    NULLIF(trim(sketchpath), '') AS sketchpath
                FROM read_parquet('{self.r2}/improvements.parquet')
                WHERE ParcelNumber IS NOT NULL
            ),
            raw AS (
                SELECT
                    * EXCLUDE (new_const_year_raw, effective_yr_blt_raw, actual_year_built_raw),
                    CASE
                        WHEN new_const_year_raw BETWEEN 1800 AND date_part('year', current_date)::INTEGER
                        THEN new_const_year_raw ELSE NULL
                    END AS new_const_year,
                    CASE
                        WHEN effective_yr_blt_raw BETWEEN 1800 AND date_part('year', current_date)::INTEGER
                        THEN effective_yr_blt_raw ELSE NULL
                    END AS effective_yr_blt,
                    CASE
                        WHEN actual_year_built_raw BETWEEN 1800 AND date_part('year', current_date)::INTEGER
                        THEN actual_year_built_raw ELSE NULL
                    END AS actual_year_built
                FROM raw_pre
            ),
            building_level AS (
                SELECT
                    parcel_number,
                    imprv_id,
                    ANY_VALUE(description) AS primary_improvement_description,
                    ANY_VALUE(building_style) AS primary_building_style,
                    ANY_VALUE(comment) AS improvement_comment,
                    MAX(imprv_val) AS building_improvement_value,
                    MAX(tot_living_area) AS building_living_area,
                    MIN(actual_year_built) AS actual_year_built,
                    MIN(effective_yr_blt) AS effective_year_built,
                    MIN(new_const_year) AS new_const_year,
                    string_agg(DISTINCT imprv_det_type_cd, ' | ') AS improvement_detail_types,
                    string_agg(DISTINCT condition_cd, ' | ') AS condition_codes,
                    ANY_VALUE(construction_style) AS construction_style,
                    ANY_VALUE(foundation) AS foundation,
                    ANY_VALUE(exterior_wall) AS exterior_wall,
                    ANY_VALUE(roof_covering) AS roof_covering,
                    ANY_VALUE(roof_style) AS roof_style,
                    ANY_VALUE(heating_cooling) AS heating_cooling,
                    ANY_VALUE(plumbing) AS plumbing,
                    ANY_VALUE(bedrooms_raw) AS bedrooms_raw,
                    ANY_VALUE(sketchpath) AS sketchpath,
                    COUNT(*) AS improvement_detail_row_count,
                    COUNT(DISTINCT segment_id) AS segment_count,
                    SUM(calc_area) FILTER (WHERE imprv_det_type_cd = 'MA') AS main_area_calc_area,
                    SUM(calc_area) FILTER (WHERE imprv_det_type_cd IN ('AGAR', 'GAR')) AS garage_area,
                    SUM(calc_area) FILTER (WHERE imprv_det_type_cd = 'DECK') AS deck_area
                FROM raw
                WHERE imprv_id IS NOT NULL
                GROUP BY parcel_number, imprv_id
            ),
            ranked_buildings AS (
                SELECT
                    *,
                    row_number() OVER (
                        PARTITION BY parcel_number
                        ORDER BY building_living_area DESC NULLS LAST,
                                 building_improvement_value DESC NULLS LAST,
                                 imprv_id DESC NULLS LAST
                    ) AS building_rank
                FROM building_level
            ),
            parcel_summary AS (
                SELECT
                    parcel_number,
                    COUNT(*) AS improvement_building_count,
                    SUM(improvement_detail_row_count) AS improvement_detail_row_count,
                    SUM(segment_count) AS improvement_segment_count,
                    SUM(building_improvement_value) AS total_improvement_value,
                    MAX(building_improvement_value) AS largest_building_improvement_value,
                    SUM(building_living_area) AS total_living_area,
                    MAX(building_living_area) AS largest_building_living_area,
                    MIN(actual_year_built) AS oldest_actual_year_built,
                    MAX(actual_year_built) AS newest_actual_year_built,
                    MIN(effective_year_built) AS oldest_effective_year_built,
                    MAX(effective_year_built) AS newest_effective_year_built,
                    SUM(main_area_calc_area) AS total_main_area_calc_area,
                    SUM(garage_area) AS total_garage_area,
                    SUM(deck_area) AS total_deck_area,
                    string_agg(DISTINCT primary_improvement_description, ' | ') AS improvement_descriptions,
                    string_agg(DISTINCT primary_building_style, ' | ') AS building_styles,
                    string_agg(DISTINCT improvement_detail_types, ' | ') AS improvement_detail_types,
                    string_agg(DISTINCT condition_codes, ' | ') AS condition_codes,
                    BOOL_OR(sketchpath IS NOT NULL) AS has_sketch
                FROM building_level
                GROUP BY parcel_number
            ),
            primary_building AS (
                SELECT
                    parcel_number,
                    primary_improvement_description,
                    primary_building_style,
                    improvement_comment,
                    building_improvement_value AS primary_building_improvement_value,
                    building_living_area AS primary_building_living_area,
                    actual_year_built AS primary_actual_year_built,
                    effective_year_built AS primary_effective_year_built,
                    construction_style AS primary_construction_style,
                    foundation AS primary_foundation,
                    exterior_wall AS primary_exterior_wall,
                    roof_covering AS primary_roof_covering,
                    roof_style AS primary_roof_style,
                    heating_cooling AS primary_heating_cooling,
                    plumbing AS primary_plumbing,
                    bedrooms_raw AS primary_bedrooms_raw,
                    sketchpath AS primary_sketchpath
                FROM ranked_buildings
                WHERE building_rank = 1
            )
            SELECT
                ps.*,
                pb.primary_improvement_description,
                pb.primary_building_style,
                pb.improvement_comment,
                pb.primary_building_improvement_value,
                pb.primary_building_living_area,
                pb.primary_actual_year_built,
                pb.primary_effective_year_built,
                CASE
                    WHEN pb.primary_actual_year_built IS NOT NULL
                    THEN date_part('year', current_date)::INTEGER - pb.primary_actual_year_built
                    ELSE NULL
                END AS primary_building_age,
                pb.primary_construction_style,
                pb.primary_foundation,
                pb.primary_exterior_wall,
                pb.primary_roof_covering,
                pb.primary_roof_style,
                pb.primary_heating_cooling,
                pb.primary_plumbing,
                pb.primary_bedrooms_raw,
                pb.primary_sketchpath
            FROM parcel_summary ps
            LEFT JOIN primary_building pb USING (parcel_number)
        )
        TO '{self.r2}/derived/parcel_improvement_summary.parquet'
        (FORMAT PARQUET);
        """)

    def build_parcel_search(self) -> None:
        self.con.execute(f"""
        COPY (
            WITH assessor_ranked AS (
                SELECT
                    *,
                    row_number() OVER (
                        PARTITION BY upper(trim("Parcel Number"))
                        ORDER BY TRY_CAST("AID" AS BIGINT) DESC NULLS LAST
                    ) AS rn
                FROM read_parquet('{self.r2}/assessor.parquet')
                WHERE "Parcel Number" IS NOT NULL
            ),
            assessor AS (
                SELECT
                    upper(trim("Parcel Number")) AS parcel_number,
                    TRY_CAST("AID" AS BIGINT) AS aid,
                    concat_ws(' ', NULLIF(trim("Situs Street Number"), ''), NULLIF(trim("Situs Street Name"), '')) AS situs_address,
                    "Situs City State Zip" AS situs_city_state_zip,
                    "Owner Name" AS owner_name,
                    "Land Use" AS land_use,
                    TRY_CAST("Acres" AS DOUBLE) AS acres,
                    TRY_CAST("Year Built" AS INTEGER) AS assessor_year_built,
                    TRY_CAST("Building Value" AS DOUBLE) AS assessor_building_value,
                    TRY_CAST("Impr Land Value" AS DOUBLE) AS improved_land_value,
                    TRY_CAST("Assessed Value" AS DOUBLE) AS assessed_value
                FROM assessor_ranked
                WHERE rn = 1
            )
            SELECT
                a.*,
                CASE WHEN NULLIF(trim(a.situs_address), '') IS NOT NULL THEN TRUE ELSE FALSE END AS has_situs_address,
                g.gis_x,
                g.gis_y,
                COALESCE(g.has_geometry, FALSE) AS has_geometry,
                COALESCE(g.pnumber_record_count, 0) AS pnumber_record_count,
                g.comp_plan_lud,
                g.zoning_code_short,
                g.zoning_label,
                g.zoning_code,
                COALESCE(g.comp_plan_hit_count, 0) AS comp_plan_hit_count,
                g.city_name,
                COALESCE(g.inside_city_limits, FALSE) AS inside_city_limits,
                COALESCE(g.city_hit_count, 0) AS city_hit_count,
                g.fire_district,
                g.school_district_num,
                g.school_district_name,
                g.commissioner_district,
                g.commissioner_name,
                g.library_district,
                g.library_service_area,
                COALESCE(s.sale_record_count, 0) AS sale_record_count,
                COALESCE(s.positive_price_sale_count, 0) AS positive_price_sale_count,
                COALESCE(s.valid_sale_count, 0) AS valid_sale_count,
                COALESCE(s.valid_warranty_sale_count, 0) AS valid_warranty_sale_count,
                s.first_deed_date,
                s.last_deed_date,
                s.last_transfer_deed_date,
                s.last_transfer_price,
                s.last_transfer_type,
                s.last_transfer_deed_type,
                s.last_transfer_recording_number,
                s.last_transfer_seller,
                s.last_transfer_buyer,
                s.last_valid_sale_date,
                s.last_valid_sale_price,
                s.last_valid_sale_deed_type,
                s.last_valid_sale_recording_number,
                s.last_valid_sale_seller,
                s.last_valid_sale_buyer,
                s.last_valid_warranty_sale_date,
                s.last_valid_warranty_sale_price,
                s.last_valid_warranty_sale_recording_number,
                s.years_since_last_valid_sale,
                CASE WHEN s.valid_sale_count > 0 THEN TRUE ELSE FALSE END AS has_valid_sale,
                CASE
                    WHEN s.last_valid_sale_date IS NOT NULL AND s.last_valid_sale_date >= current_date - INTERVAL 365 DAY
                    THEN TRUE ELSE FALSE
                END AS sold_last_12_months,
                CASE
                    WHEN s.last_valid_sale_date IS NOT NULL AND s.last_valid_sale_date >= current_date - INTERVAL 5 YEAR
                    THEN TRUE ELSE FALSE
                END AS sold_last_5_years,
                COALESCE(i.improvement_building_count, 0) AS improvement_building_count,
                COALESCE(i.improvement_detail_row_count, 0) AS improvement_detail_row_count,
                COALESCE(i.improvement_segment_count, 0) AS improvement_segment_count,
                i.total_improvement_value,
                i.largest_building_improvement_value,
                i.total_living_area,
                i.largest_building_living_area,
                i.oldest_actual_year_built,
                i.newest_actual_year_built,
                i.oldest_effective_year_built,
                i.newest_effective_year_built,
                i.total_main_area_calc_area,
                i.total_garage_area,
                i.total_deck_area,
                i.improvement_descriptions,
                i.building_styles,
                i.improvement_detail_types,
                i.condition_codes,
                COALESCE(i.has_sketch, FALSE) AS has_sketch,
                i.primary_improvement_description,
                i.primary_building_style,
                i.improvement_comment,
                i.primary_building_improvement_value,
                i.primary_building_living_area,
                i.primary_actual_year_built,
                i.primary_effective_year_built,
                i.primary_building_age,
                i.primary_construction_style,
                i.primary_foundation,
                i.primary_exterior_wall,
                i.primary_roof_covering,
                i.primary_roof_style,
                i.primary_heating_cooling,
                i.primary_plumbing,
                i.primary_bedrooms_raw,
                i.primary_sketchpath,
                CASE WHEN i.parcel_number IS NOT NULL THEN TRUE ELSE FALSE END AS has_improvement_record
            FROM assessor a
            LEFT JOIN read_parquet('{self.r2}/derived/parcel_geo_flags.parquet') g USING (parcel_number)
            LEFT JOIN read_parquet('{self.r2}/derived/parcel_sales_summary.parquet') s USING (parcel_number)
            LEFT JOIN read_parquet('{self.r2}/derived/parcel_improvement_summary.parquet') i USING (parcel_number)
        )
        TO '{self.r2}/derived/parcel_search.parquet'
        (FORMAT PARQUET);
        """)

    def validate_parcel_search(self) -> pd.DataFrame:
        return self.con.execute(f"""
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT parcel_number) AS distinct_parcels,
            COUNT(*) FILTER (WHERE has_situs_address = TRUE) AS has_situs_address,
            COUNT(*) FILTER (WHERE has_geometry = TRUE) AS has_geometry,
            COUNT(*) FILTER (WHERE comp_plan_lud IS NOT NULL) AS has_comp_plan,
            COUNT(*) FILTER (WHERE inside_city_limits = TRUE) AS inside_city_limits,
            COUNT(*) FILTER (WHERE assessed_value IS NOT NULL) AS has_assessed_value,
            COUNT(*) FILTER (WHERE acres IS NOT NULL) AS has_acres,
            COUNT(*) FILTER (WHERE has_valid_sale = TRUE) AS has_valid_sale,
            COUNT(*) FILTER (WHERE sold_last_12_months = TRUE) AS sold_last_12_months,
            COUNT(*) FILTER (WHERE sold_last_5_years = TRUE) AS sold_last_5_years,
            COUNT(*) FILTER (WHERE has_improvement_record = TRUE) AS has_improvement_record,
            COUNT(*) FILTER (WHERE primary_actual_year_built IS NOT NULL) AS has_primary_actual_year_built,
            MIN(primary_actual_year_built) AS oldest_primary_actual_year_built,
            MAX(primary_actual_year_built) AS newest_primary_actual_year_built
        FROM read_parquet('{self.r2}/derived/parcel_search.parquet');
        """).df()

    def validate_duplicates(self, path: str = "derived/parcel_search.parquet") -> pd.DataFrame:
        full_path = path if path.startswith("r2://") else f"{self.r2}/{path}"
        return self.con.execute(f"""
        SELECT parcel_number, COUNT(*) AS row_count
        FROM read_parquet('{full_path}')
        GROUP BY parcel_number
        HAVING COUNT(*) > 1
        ORDER BY row_count DESC, parcel_number
        LIMIT 50;
        """).df()

    def validate_all(self) -> dict[str, pd.DataFrame]:
        return {
            "parcel_search": self.validate_parcel_search(),
            "parcel_search_duplicates": self.validate_duplicates(),
        }

    def run_all(self) -> dict[str, pd.DataFrame]:
        print("Connecting to R2...")
        self.connect()
        print("Building derived/parcel_geo_flags.parquet...")
        self.build_geo_flags()
        print("Building derived/parcel_sales_summary.parquet...")
        self.build_sales_summary()
        print("Building derived/parcel_improvement_summary.parquet...")
        self.build_improvement_summary()
        print("Building derived/parcel_search.parquet...")
        self.build_parcel_search()
        print("Validating outputs...")
        results = self.validate_all()
        for name, df in results.items():
            print(f"\n{name}")
            print(df)
        return results
