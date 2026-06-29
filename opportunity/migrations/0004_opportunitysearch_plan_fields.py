from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opportunity", "0003_opportunitysearch_feedback"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunitysearch",
            name="plan_review",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="opportunitysearch",
            name="result_diagnostics",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="opportunitysearch",
            name="search_plan",
            field=models.JSONField(default=dict),
        ),
    ]
