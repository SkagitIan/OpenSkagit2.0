from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("opportunity", "0002_parcelbooksyncnarrative"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpportunitySearch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prompt", models.TextField()),
                ("title", models.TextField(blank=True)),
                ("criteria_summary", models.TextField(blank=True)),
                ("assumptions", models.JSONField(default=list)),
                ("generated_sql", models.TextField(blank=True)),
                ("generated_params", models.JSONField(default=list)),
                ("model", models.TextField(blank=True)),
                ("result_rows", models.JSONField(default=list)),
                ("result_count", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("ready", "Ready"), ("error", "Error")], default="draft", max_length=16)),
                ("error", models.TextField(blank=True)),
                ("saved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="opportunity_searches", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(fields=["user", "-updated_at"], name="opp_search_user_updated_idx"),
                    models.Index(fields=["user", "-saved_at"], name="opp_search_user_saved_idx"),
                    models.Index(fields=["status", "-updated_at"], name="opp_search_status_upd_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpportunitySearchFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.CharField(choices=[("good", "Good match"), ("bad", "Bad match")], max_length=12)),
                ("parcel_number", models.TextField(blank=True)),
                ("reason_code", models.CharField(blank=True, choices=[("too_broad", "Too broad"), ("too_narrow", "Too narrow"), ("wrong_location", "Wrong location"), ("wrong_parcel_type", "Wrong parcel type"), ("missing_utilities", "Missing utilities"), ("already_improved", "Already improved"), ("bad_data", "Bad data"), ("other", "Other")], max_length=32)),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("search", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feedback", to="opportunity.opportunitysearch")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="opportunity_search_feedback", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(fields=["user", "-updated_at"], name="opp_fb_user_updated_idx"),
                    models.Index(fields=["search", "rating"], name="opp_fb_search_rating_idx"),
                    models.Index(fields=["parcel_number"], name="opp_fb_parcel_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="opportunitysearchfeedback",
            constraint=models.UniqueConstraint(fields=("user", "search", "parcel_number"), name="uniq_opportunity_search_feedback_scope"),
        ),
    ]
