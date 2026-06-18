from django.db import migrations


VIEW_SQL = """
CREATE OR REPLACE VIEW v_city_stats AS
WITH city_map(slug, name, district_name) AS (
    VALUES
        ('sedro-woolley', 'Sedro-Woolley', 'Sedro Woolley'),
        ('burlington', 'Burlington', 'Burlington'),
        ('mount-vernon', 'Mount Vernon', 'Mount Vernon'),
        ('anacortes', 'Anacortes', 'Anacortes'),
        ('concrete', 'Concrete', 'Concrete'),
        ('la-conner', 'La Conner', 'La Conner'),
        ('hamilton', 'Hamilton', 'Hamilton'),
        ('lyman', 'Lyman', 'Lyman')
),
city_parcels AS (
    SELECT
        cm.slug,
        cm.name,
        ar.parcel_number,
        ar.proptype,
        ar.total_market_value_num
    FROM city_map cm
    LEFT JOIN assessor_rollup ar
      ON upper(coalesce(ar.city_district, '')) = upper(cm.district_name)
),
city_sales AS (
    SELECT
        cp.slug,
        cp.proptype,
        s.sale_price_num,
        CASE
            WHEN s.sale_date_iso ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN s.sale_date_iso::date
            ELSE NULL
        END AS sale_date
    FROM city_parcels cp
    JOIN sales s
      ON s.parcel_number = cp.parcel_number
    WHERE s.sale_price_num IS NOT NULL
      AND s.sale_price_num > 0
      AND coalesce(s.sale_type, '') = 'VALID SALE'
),
parcel_stats AS (
    SELECT
        slug,
        count(parcel_number)::integer AS parcel_count,
        avg(total_market_value_num) FILTER (
            WHERE proptype = 'R' AND total_market_value_num > 0
        ) AS avg_home_value
    FROM city_parcels
    GROUP BY slug
),
sales_stats AS (
    SELECT
        slug,
        count(sale_price_num) FILTER (
            WHERE sale_date >= current_date - interval '90 days'
        )::integer AS recent_sales_90,
        avg(sale_price_num) FILTER (
            WHERE proptype = 'R'
              AND sale_date >= current_date - interval '90 days'
        ) AS avg_home_sale_price
    FROM city_sales
    GROUP BY slug
)
SELECT
    cm.slug,
    cm.name,
    cm.district_name,
    coalesce(ps.parcel_count, 0)::integer AS parcel_count,
    coalesce(ss.recent_sales_90, 0)::integer AS recent_sales_90,
    ps.avg_home_value,
    ss.avg_home_sale_price
FROM city_map cm
LEFT JOIN parcel_stats ps
  ON ps.slug = cm.slug
LEFT JOIN sales_stats ss
  ON ss.slug = cm.slug;

CREATE OR REPLACE VIEW v_city_stats_sedro_woolley AS
SELECT * FROM v_city_stats WHERE slug = 'sedro-woolley';

CREATE OR REPLACE VIEW v_city_stats_burlington AS
SELECT * FROM v_city_stats WHERE slug = 'burlington';

CREATE OR REPLACE VIEW v_city_stats_mount_vernon AS
SELECT * FROM v_city_stats WHERE slug = 'mount-vernon';

CREATE OR REPLACE VIEW v_city_stats_anacortes AS
SELECT * FROM v_city_stats WHERE slug = 'anacortes';

CREATE OR REPLACE VIEW v_city_stats_concrete AS
SELECT * FROM v_city_stats WHERE slug = 'concrete';

CREATE OR REPLACE VIEW v_city_stats_la_conner AS
SELECT * FROM v_city_stats WHERE slug = 'la-conner';

CREATE OR REPLACE VIEW v_city_stats_hamilton AS
SELECT * FROM v_city_stats WHERE slug = 'hamilton';

CREATE OR REPLACE VIEW v_city_stats_lyman AS
SELECT * FROM v_city_stats WHERE slug = 'lyman';
"""

DROP_SQL = """
DROP VIEW IF EXISTS v_city_stats_lyman;
DROP VIEW IF EXISTS v_city_stats_hamilton;
DROP VIEW IF EXISTS v_city_stats_la_conner;
DROP VIEW IF EXISTS v_city_stats_concrete;
DROP VIEW IF EXISTS v_city_stats_anacortes;
DROP VIEW IF EXISTS v_city_stats_mount_vernon;
DROP VIEW IF EXISTS v_city_stats_burlington;
DROP VIEW IF EXISTS v_city_stats_sedro_woolley;
DROP VIEW IF EXISTS v_city_stats;
"""


def create_city_stat_views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for statement in VIEW_SQL.split(";"):
            if statement.strip():
                cursor.execute(statement)


def drop_city_stat_views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for statement in DROP_SQL.split(";"):
            if statement.strip():
                cursor.execute(statement)


class Migration(migrations.Migration):
    dependencies = []

    operations = [
        migrations.RunPython(create_city_stat_views, drop_city_stat_views),
    ]
