from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opportunity", "0011_opportunity_current_parcels"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunitysearch",
            name="search_mode",
            field=models.CharField(
                choices=[("search", "Find matching parcels"), ("investigate", "Investigate opportunities")],
                default="search",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="opportunitysearch",
            name="investigation_status",
            field=models.CharField(default="not_started", max_length=16),
        ),
        migrations.AddField(
            model_name="opportunitysearch",
            name="investigation_options",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="opportunitysearch",
            name="investigation_result",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="opportunitysearch",
            name="investigation_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
