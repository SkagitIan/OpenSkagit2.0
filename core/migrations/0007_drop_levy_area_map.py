from django.db import migrations


DROP_SQL = """
DROP TABLE IF EXISTS levy_area_map;
"""

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS levy_area_map (
    levy_code TEXT PRIMARY KEY,
    area_label TEXT NOT NULL,
    parcel_count INTEGER NOT NULL DEFAULT 0,
    median_rate NUMERIC,
    geometry geometry(MultiPolygon, 4326),
    rebuilt_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS levy_area_map_geom_idx
    ON levy_area_map USING GIST (geometry);
"""


def run_statements(schema_editor, sql):
    with schema_editor.connection.cursor() as cursor:
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)


def drop_levy_area_map(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    run_statements(schema_editor, DROP_SQL)


def recreate_levy_area_map(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    run_statements(schema_editor, CREATE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_levy_area_map"),
    ]

    operations = [
        migrations.RunPython(drop_levy_area_map, recreate_levy_area_map),
    ]
