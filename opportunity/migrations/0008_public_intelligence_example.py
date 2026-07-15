from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("opportunity", "0007_opportunitysearch_short_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicIntelligenceExample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=96, unique=True)),
                ("question", models.TextField()),
                ("public_title", models.TextField(blank=True)),
                ("source_context", models.JSONField(default=list)),
                ("result_count", models.PositiveIntegerField(default=0)),
                ("count_is_capped", models.BooleanField(default=False)),
                ("refreshed_at", models.DateTimeField(blank=True, null=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("status", models.CharField(default="ready", max_length=16)),
                ("search", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="public_intelligence_examples", to="opportunity.opportunitysearch")),
            ],
            options={
                "ordering": ["sort_order", "slug"],
                "indexes": [
                    models.Index(fields=["is_active", "sort_order"], name="opportunity_public_is_active_8f72d0_idx"),
                    models.Index(fields=["status", "is_active"], name="opportunity_public_status_0e0b3a_idx"),
                ],
            },
        ),
    ]
