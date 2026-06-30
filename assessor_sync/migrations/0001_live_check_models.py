import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Declares all assessor_sync models in Django's migration state.

    The managed=False models already exist as raw SQL tables; no DDL is
    generated for them.  They must appear here so that cross-app FK
    references (e.g. opportunity.ParcelBookSyncNarrative → AssessorSyncReport)
    resolve correctly in migration state validation.

    LiveCheckRun and ParcelLiveSnapshot are managed=True and are created here.
    """

    initial = True

    dependencies = []

    operations = [
        # ----------------------------------------------------------------
        # Existing unmanaged tables — state-only, no DDL
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="AssessorSyncRun",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("source_url", models.TextField(blank=True, null=True)),
                ("zip_sha256", models.TextField(blank=True, null=True)),
                ("status", models.TextField()),
                ("report_path", models.TextField(blank=True, null=True)),
                ("summary", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True, null=True)),
            ],
            options={
                "managed": False,
                "db_table": "assessor_sync_runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="AssessorSyncFile",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run", models.ForeignKey(
                    db_column="run_id",
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="files",
                    to="assessor_sync.assessorsyncrun",
                )),
                ("file_name", models.TextField()),
                ("sha256", models.TextField()),
                ("byte_size", models.BigIntegerField()),
                ("changed", models.BooleanField()),
                ("previous_sha256", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField()),
            ],
            options={
                "managed": False,
                "db_table": "assessor_sync_files",
                "ordering": ["run_id", "file_name"],
            },
        ),
        migrations.CreateModel(
            name="AssessorSyncChange",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run", models.ForeignKey(
                    db_column="run_id",
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="changes",
                    to="assessor_sync.assessorsyncrun",
                )),
                ("table_name", models.TextField()),
                ("record_key", models.TextField()),
                ("change_type", models.TextField()),
                ("changed_fields", models.JSONField(default=dict)),
                ("old_row", models.JSONField(blank=True, null=True)),
                ("new_row", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField()),
            ],
            options={
                "managed": False,
                "db_table": "assessor_sync_changes",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AssessorSyncReport",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run", models.ForeignKey(
                    db_column="run_id",
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="reports",
                    to="assessor_sync.assessorsyncrun",
                )),
                ("report_text", models.TextField()),
                ("created_at", models.DateTimeField()),
            ],
            options={
                "managed": False,
                "db_table": "assessor_sync_reports",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditorRecording",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recording_number", models.TextField(unique=True)),
                ("recorded_date", models.DateField(blank=True, null=True)),
                ("document_type", models.TextField()),
                ("signal_group", models.TextField()),
                ("grantor", models.TextField(blank=True)),
                ("grantee", models.TextField(blank=True)),
                ("filer", models.TextField(blank=True)),
                ("comment", models.TextField(blank=True)),
                ("legal", models.TextField(blank=True)),
                ("parcel_number", models.TextField(blank=True)),
                ("parcel_text", models.TextField(blank=True)),
                ("assessor_url", models.TextField(blank=True)),
                ("pdf_url", models.TextField(blank=True)),
                ("reference_url", models.TextField(blank=True)),
                ("raw_row", models.JSONField(default=dict)),
                ("first_seen_run", models.ForeignKey(
                    blank=True,
                    db_column="first_seen_run_id",
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="first_seen_auditor_recordings",
                    to="assessor_sync.assessorsyncrun",
                )),
                ("last_seen_run", models.ForeignKey(
                    blank=True,
                    db_column="last_seen_run_id",
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="last_seen_auditor_recordings",
                    to="assessor_sync.assessorsyncrun",
                )),
                ("first_seen_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField()),
            ],
            options={
                "managed": False,
                "db_table": "auditor_recordings",
                "ordering": ["-recorded_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="AuditorSyncQuery",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run", models.ForeignKey(
                    db_column="run_id",
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="auditor_queries",
                    to="assessor_sync.assessorsyncrun",
                )),
                ("document_type", models.TextField()),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("result_count", models.IntegerField()),
                ("parsed_count", models.IntegerField()),
                ("page_count", models.IntegerField()),
                ("inserted_count", models.IntegerField()),
                ("updated_count", models.IntegerField()),
                ("status", models.TextField()),
                ("capped", models.BooleanField()),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "managed": False,
                "db_table": "auditor_sync_queries",
                "ordering": ["-created_at", "document_type"],
            },
        ),
        # ----------------------------------------------------------------
        # New managed tables — DDL is executed
        # ----------------------------------------------------------------
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
