from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_land_ledger_phase2_columns"),
    ]

    operations = [
        migrations.CreateModel(
            name="CurrentDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("rejected", "Rejected"), ("archived", "Archived"), ("published", "Published")], default="draft", max_length=20)),
                ("probe", models.TextField()),
                ("model", models.TextField(blank=True)),
                ("question", models.TextField()),
                ("short_answer", models.TextField(blank=True)),
                ("why_it_matters", models.TextField(blank=True)),
                ("confidence", models.IntegerField(blank=True, null=True)),
                ("publish_score", models.IntegerField(blank=True, null=True)),
                ("source_data", models.TextField(blank=True)),
                ("caveats", models.JSONField(blank=True, default=list)),
                ("what_to_check_next", models.TextField(blank=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("row_count", models.IntegerField(default=0)),
                ("qa_flags", models.JSONField(blank=True, default=list)),
                ("probe_metadata", models.JSONField(blank=True, default=dict)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-publish_score", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="currentdraft",
            index=models.Index(fields=["status", "publish_score"], name="core_curren_status_56e2d4_idx"),
        ),
        migrations.AddIndex(
            model_name="currentdraft",
            index=models.Index(fields=["probe", "created_at"], name="core_curren_probe_6e02bc_idx"),
        ),
    ]
