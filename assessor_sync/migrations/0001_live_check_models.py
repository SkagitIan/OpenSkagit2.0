from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="LiveCheckRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.TextField(default="running")),
                ("summary", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True)),
            ],
            options={
                "db_table": "assessor_live_check_runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="ParcelLiveSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("parcel_number", models.TextField(unique=True)),
                ("tracked_fields", models.JSONField(default=dict)),
                ("last_checked_at", models.DateTimeField()),
                ("last_changed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "assessor_parcel_live_snapshots",
                "ordering": ["-last_checked_at"],
            },
        ),
    ]
