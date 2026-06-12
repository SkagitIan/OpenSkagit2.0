from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS postgis;",
            reverse_sql="SELECT 1;",  # postgis removal is destructive — no-op on reverse
        ),
    ]
