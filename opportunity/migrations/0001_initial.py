from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OpportunitySavedParcel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("parcel_number", models.TextField()),
                ("source_tab", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="opportunity_saved_parcels", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(fields=["user", "-updated_at"], name="opportunity_user_id_443c67_idx"),
                    models.Index(fields=["parcel_number"], name="opportunity_parcel__4fb76c_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "parcel_number"), name="uniq_opportunity_saved_user_parcel"),
                ],
            },
        ),
    ]
