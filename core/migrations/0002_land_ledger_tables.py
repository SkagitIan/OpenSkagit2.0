from django.db import migrations


CREATE_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS land_ledger_parcels (
    city_slug TEXT NOT NULL,
    city_name TEXT NOT NULL,
    parcel_number TEXT NOT NULL,
    address TEXT,
    acres NUMERIC,
    land_use TEXT,
    category TEXT,
    zone_id TEXT,
    zone_name TEXT,
    zone_group TEXT,
    current_tax NUMERIC,
    tax_per_acre NUMERIC,
    city_tax_pct NUMERIC,
    allowed_scenarios JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_scenarios JSONB NOT NULL DEFAULT '[]'::jsonb,
    scenario_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    policy_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    benchmark_source JSONB NOT NULL DEFAULT '{}'::jsonb,
    geometry geometry(MultiPolygon, 4326),
    rebuilt_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (city_slug, parcel_number)
);

CREATE INDEX IF NOT EXISTS land_ledger_parcels_city_idx
    ON land_ledger_parcels (city_slug);

CREATE INDEX IF NOT EXISTS land_ledger_parcels_zone_idx
    ON land_ledger_parcels (city_slug, zone_id);

CREATE INDEX IF NOT EXISTS land_ledger_parcels_geom_idx
    ON land_ledger_parcels USING GIST (geometry);

CREATE TABLE IF NOT EXISTS land_ledger_city_summary (
    city_slug TEXT PRIMARY KEY,
    city_name TEXT NOT NULL,
    parcel_count INTEGER NOT NULL DEFAULT 0,
    zoned_count INTEGER NOT NULL DEFAULT 0,
    unknown_zone_count INTEGER NOT NULL DEFAULT 0,
    current_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    policy_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
    scenario_definitions JSONB NOT NULL DEFAULT '{}'::jsonb,
    zone_descriptions JSONB NOT NULL DEFAULT '{}'::jsonb,
    buildout_factor NUMERIC NOT NULL DEFAULT 0.5,
    horizon_years INTEGER NOT NULL DEFAULT 10,
    rebuilt_at TIMESTAMPTZ NOT NULL
);

CREATE OR REPLACE VIEW v_land_ledger_source AS
WITH city_map(city_slug, city_name, district_name, city_mcag) AS (
    VALUES
        ('sedro-woolley', 'Sedro-Woolley', 'Sedro Woolley', '0647'),
        ('burlington', 'Burlington', 'Burlington', '0633'),
        ('mount-vernon', 'Mount Vernon', 'Mount Vernon', '0644'),
        ('anacortes', 'Anacortes', 'Anacortes', '0628'),
        ('concrete', 'Concrete', 'Concrete', '0636'),
        ('la-conner', 'La Conner', 'La Conner', '0640'),
        ('hamilton', 'Hamilton', 'Hamilton', '0638'),
        ('lyman', 'Lyman', 'Lyman', '0642')
),
parcel_zoning_ranked AS (
    SELECT
        pz.*,
        row_number() OVER (
            PARTITION BY upper(trim(pz.parcel_id))
            ORDER BY coalesce(pz.is_primary, false) DESC,
                     coalesce(pz.percent_of_parcel, 0) DESC,
                     coalesce(pz.overlap_area_sqft, 0) DESC
        ) AS ledger_rn
    FROM parcel_zoning pz
),
tax_totals AS (
    SELECT parcel_number, sum(total_tax) AS total_tax
    FROM v_parcel_tax_summary
    GROUP BY parcel_number
),
city_tax AS (
    SELECT pts.parcel_number, cm.city_slug, sum(pts.total_tax) AS city_tax
    FROM v_parcel_tax_summary pts
    JOIN city_map cm
      ON cm.city_mcag IS NOT NULL
     AND pts.mcag = cm.city_mcag
    GROUP BY pts.parcel_number, cm.city_slug
)
SELECT
    cm.city_slug,
    cm.city_name,
    sp.parcel_number,
    nullif(trim(concat_ws(' ', sp.situs_street_number, sp.situs_street_name)), '') AS address,
    sp.acres,
    sp.land_use,
    sp.total_taxes,
    CASE
        WHEN tt.total_tax > 0 THEN coalesce(ct.city_tax, 0) / tt.total_tax * 100
        ELSE 0
    END AS city_tax_pct,
    coalesce(ppz.zone_id, pzr.zone_id, spatial_zone.zone_id) AS zone_id,
    coalesce(ppz.zone_name, pzr.zone_name, spatial_zone.zone_name) AS zone_name,
    CASE
        WHEN coalesce(ppz.zone_id, pzr.zone_id, spatial_zone.zone_id) IS NULL THEN 'other'
        WHEN upper(coalesce(ppz.zone_id, pzr.zone_id, spatial_zone.zone_id)) LIKE 'R-%' THEN 'residential'
        WHEN upper(coalesce(ppz.zone_id, pzr.zone_id, spatial_zone.zone_id)) IN ('CBD', 'MC') THEN 'commercial'
        WHEN upper(coalesce(ppz.zone_id, pzr.zone_id, spatial_zone.zone_id)) = 'I' THEN 'industrial'
        WHEN upper(coalesce(ppz.zone_id, pzr.zone_id, spatial_zone.zone_id)) IN ('P', 'OS') THEN 'public'
        ELSE 'other'
    END AS zone_group,
    ST_Multi(ST_Transform(gsp.geometry, 4326))::geometry(MultiPolygon, 4326) AS geometry
FROM city_map cm
JOIN skagit_parcels sp
  ON upper(coalesce(sp.city_district, '')) = upper(cm.district_name)
 AND sp.inactive_date IS NULL
 AND sp.acres IS NOT NULL
 AND sp.acres > 0
 AND sp.total_taxes IS NOT NULL
JOIN gis_skagit_parcels gsp
  ON upper(trim(gsp.parcel_id)) = upper(trim(sp.parcel_number))
 AND gsp.geometry IS NOT NULL
LEFT JOIN parcel_primary_zoning ppz
  ON upper(trim(ppz.parcel_id)) = upper(trim(sp.parcel_number))
LEFT JOIN parcel_zoning_ranked pzr
  ON upper(trim(pzr.parcel_id)) = upper(trim(sp.parcel_number))
 AND pzr.ledger_rn = 1
LEFT JOIN tax_totals tt
  ON tt.parcel_number = sp.parcel_number
LEFT JOIN city_tax ct
  ON ct.parcel_number = sp.parcel_number
 AND ct.city_slug = cm.city_slug
LEFT JOIN LATERAL (
    SELECT wzz.zone_id, wzz.zone_name
    FROM waza_zoning_zones wzz
    WHERE ppz.zone_id IS NULL
      AND pzr.zone_id IS NULL
      AND wzz.geometry IS NOT NULL
      AND ST_Intersects(ST_Transform(gsp.geometry, 4326), ST_Transform(wzz.geometry, 4326))
    ORDER BY ST_Area(ST_Intersection(ST_Transform(gsp.geometry, 4326), ST_Transform(wzz.geometry, 4326))) DESC
    LIMIT 1
) spatial_zone ON true;
"""

DROP_SQL = """
DROP VIEW IF EXISTS v_land_ledger_source;
DROP TABLE IF EXISTS land_ledger_city_summary;
DROP TABLE IF EXISTS land_ledger_parcels;
"""


def run_statements(schema_editor, sql):
    with schema_editor.connection.cursor() as cursor:
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)


def create_land_ledger_schema(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    run_statements(schema_editor, CREATE_SQL)


def drop_land_ledger_schema(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    run_statements(schema_editor, DROP_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_city_stat_views"),
    ]

    operations = [
        migrations.RunPython(create_land_ledger_schema, drop_land_ledger_schema),
    ]
