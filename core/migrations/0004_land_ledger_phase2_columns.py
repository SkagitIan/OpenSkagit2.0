from django.db import migrations


SQL = """
ALTER TABLE land_ledger_parcels
    ADD COLUMN IF NOT EXISTS productivity_percentile NUMERIC,
    ADD COLUMN IF NOT EXISTS productivity_label TEXT,
    ADD COLUMN IF NOT EXISTS city_current_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS city_policy_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS exclusion_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS model_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS assumption_version TEXT;

ALTER TABLE land_ledger_city_summary
    ADD COLUMN IF NOT EXISTS city_current_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS city_policy_opportunity_10yr NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS eligible_parcel_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS excluded_parcel_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scenario_totals JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS exclusion_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS assumption_version TEXT;
"""


def add_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_land_ledger_source_values"),
    ]

    operations = [
        migrations.RunPython(add_columns, migrations.RunPython.noop),
    ]
