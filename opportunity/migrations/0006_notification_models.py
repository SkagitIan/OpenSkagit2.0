from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("opportunity", "0005_sync_brief_newsletter_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserNotificationPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notify_watchlist", models.BooleanField(default=False)),
                ("digest_cadence", models.CharField(
                    choices=[("daily", "Daily digest"), ("weekly", "Weekly digest")],
                    default="daily",
                    max_length=8,
                )),
                ("notify_brief", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_pref",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EmailTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(
                    choices=[("watchlist_digest", "Watchlist change digest"), ("daily_brief", "Daily brief / newsletter")],
                    max_length=32,
                    unique=True,
                )),
                ("subject", models.TextField()),
                ("body_html", models.TextField(
                    help_text="Django template syntax. Variables: {{ user }}, {{ changes }}, {{ site_url }} for digest; {{ user }}, {{ narrative }}, {{ site_url }} for brief."
                )),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ParcelWatchNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("parcel_number", models.TextField(blank=True)),
                ("trigger_type", models.CharField(
                    choices=[
                        ("assessor_change", "Assessor data change"),
                        ("auditor_recording", "Auditor recording"),
                        ("brief", "Daily brief"),
                    ],
                    max_length=24,
                )),
                ("payload", models.JSONField(default=dict)),
                ("run_id", models.BigIntegerField()),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parcel_watch_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="parcelwatchnotification",
            constraint=models.UniqueConstraint(
                fields=["user", "parcel_number", "trigger_type", "run_id"],
                name="uniq_parcel_watch_notification",
            ),
        ),
        migrations.AddIndex(
            model_name="parcelwatchnotification",
            index=models.Index(fields=["user", "sent_at", "-created_at"], name="opp_pwn_user_sent_idx"),
        ),
        migrations.AddIndex(
            model_name="parcelwatchnotification",
            index=models.Index(fields=["trigger_type", "sent_at"], name="opp_pwn_type_sent_idx"),
        ),
    ]
