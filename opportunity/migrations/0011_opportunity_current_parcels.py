from django.db import migrations


VIEW_SQL = """
CREATE OR REPLACE VIEW opportunity_current_parcels AS
WITH fallback_ranked AS (
    SELECT
        ar.*,
        'observed_latest_assessor_roll'::text AS opportunity_value_source,
        row_number() OVER (
            PARTITION BY trim(ar.parcel_number)
            ORDER BY ar.id DESC
        ) AS parcel_rank
    FROM assessor_rollup ar
    WHERE trim(ar.appraisal_year) = (
        SELECT max(trim(appraisal_year))
        FROM assessor_rollup
        WHERE trim(appraisal_year) ~ '^[0-9]+$'
    )
),
source (
    parcel_number,
    appraisal_year,
    tax_year,
    owner_name,
    situs_street_number,
    situs_street_name,
    situs_city_state_zip,
    neighborhood_code,
    land_use_code,
    land_use_description,
    building_value,
    improved_land_value,
    unimproved_land_value,
    timber_land_value,
    assessed_value,
    taxable_value,
    total_market_value,
    acres,
    year_built,
    living_area,
    inactive_date,
    proptype,
    utilities,
    opportunity_value_source
) AS (
    SELECT
        trim(parcel_number),
        NULLIF(trim(appraisal_year), '')::integer,
        NULLIF(trim(tax_year), '')::integer,
        owner_name,
        situs_street_number,
        situs_street_name,
        situs_city_state_zip,
        neighborhood_code,
        land_use_code,
        land_use_description,
        NULLIF(regexp_replace(COALESCE(building_value, ''), '[^0-9.-]', '', 'g'), '')::numeric,
        NULLIF(regexp_replace(COALESCE(impr_land_value, ''), '[^0-9.-]', '', 'g'), '')::numeric,
        NULLIF(regexp_replace(COALESCE(unimpr_land_value, ''), '[^0-9.-]', '', 'g'), '')::numeric,
        NULLIF(regexp_replace(COALESCE(timber_land_value, ''), '[^0-9.-]', '', 'g'), '')::numeric,
        assessed_value_num::numeric,
        taxable_value_num::numeric,
        total_market_value_num::numeric,
        acres_num::numeric,
        NULLIF(regexp_replace(COALESCE(year_built, ''), '[^0-9.-]', '', 'g'), '')::integer,
        NULLIF(regexp_replace(COALESCE(living_area, ''), '[^0-9.-]', '', 'g'), '')::numeric,
        NULLIF(inactive_date, ''),
        proptype,
        utilities,
        opportunity_value_source
    FROM fallback_ranked
    WHERE parcel_rank = 1
      AND trim(parcel_number) <> ''
)
SELECT
    p.aid,
    p.parcel_number,
    p.account_number,
    p.legal_description,
    COALESCE(s.situs_street_number, p.situs_street_number) AS situs_street_number,
    COALESCE(s.situs_street_name, p.situs_street_name) AS situs_street_name,
    COALESCE(s.situs_city_state_zip, p.situs_city_state_zip) AS situs_city_state_zip,
    p.old_street_number,
    p.old_street_name,
    p.old_city_state_zip,
    COALESCE(s.owner_name, p.owner_name) AS owner_name,
    p.owner_add_1,
    p.owner_add_2,
    p.owner_add_3,
    p.owner_city,
    p.owner_state,
    p.owner_zip,
    p.exemptions,
    COALESCE(s.neighborhood_code, p.neighborhood_code) AS neighborhood_code,
    COALESCE(s.building_value, p.building_value) AS building_value,
    CASE
        WHEN s.land_use_code IS NOT NULL AND s.land_use_description IS NOT NULL
            THEN '(' || s.land_use_code || ') ' || s.land_use_description
        ELSE p.land_use
    END AS land_use,
    COALESCE(s.improved_land_value, p.impr_land_value) AS impr_land_value,
    COALESCE(s.unimproved_land_value, p.unimpr_land_value) AS unimpr_land_value,
    COALESCE(s.timber_land_value, p.timber_land_value) AS timber_land_value,
    COALESCE(s.assessed_value, p.assessed_value) AS assessed_value,
    COALESCE(s.taxable_value, p.taxable_value) AS taxable_value,
    COALESCE(s.total_market_value, p.total_market_value) AS total_market_value,
    COALESCE(s.acres, p.acres) AS acres,
    p.sale_date,
    p.sale_price,
    p.sale_deed_type,
    p.total_taxes,
    COALESCE(s.year_built, p.year_built) AS year_built,
    COALESCE(s.living_area, p.living_area) AS living_area,
    p.tot_special_assessments,
    p.general_taxes,
    CASE WHEN s.inactive_date IS NOT NULL THEN s.inactive_date::date ELSE p.inactive_date END AS inactive_date,
    p.buildingstyle,
    p.foundation,
    p.exterior_walls,
    p.roof_covering,
    p.roof_style,
    p.floor_covering,
    p.floor_construction,
    p.interior_finish,
    p.plumbing,
    p.garagesqft,
    p.heat_air_cond,
    p.fireplace,
    p.finishedbasement,
    p.number_of_bedrooms,
    p.eff_year_built,
    p.unfinishedbasement,
    p.fire_district,
    p.school_district,
    p.city_district,
    p.unit,
    p.levy_code,
    p.current_use_adjustment,
    p.tide_land_value,
    p.senior_exemption_adjustment,
    p.township,
    p.range,
    p.section,
    p.quarter_section,
    COALESCE(s.tax_year, NULLIF(p.tax_year, '')::integer)::text AS tax_year,
    COALESCE(s.appraisal_year, NULLIF(p.appraisal_year, '')::integer)::text AS appraisal_year,
    COALESCE(s.utilities, p.utilities) AS utilities,
    p.tax_statement_taxable_value,
    COALESCE(s.proptype, p.proptype) AS proptype,
    p.hasseptic,
    p.loaded_at,
    COALESCE(s.appraisal_year, NULLIF(p.appraisal_year, '')::integer) AS opportunity_appraisal_year,
    COALESCE(s.opportunity_value_source, 'legacy_parcel_values') AS opportunity_value_source
FROM skagit_parcels p
LEFT JOIN source s ON trim(s.parcel_number) = trim(p.parcel_number);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("opportunity", "0010_add_query_language"),
    ]

    operations = [
        migrations.RunSQL(VIEW_SQL, "DROP VIEW IF EXISTS opportunity_current_parcels"),
    ]
