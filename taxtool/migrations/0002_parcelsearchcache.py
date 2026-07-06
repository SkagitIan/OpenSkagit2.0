from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("taxtool", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ParcelSearchCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("parcel_number", models.CharField(max_length=32, unique=True)),
                ("situs_street_number", models.CharField(blank=True, max_length=32)),
                ("situs_street_name", models.CharField(blank=True, max_length=160)),
                ("situs_city_state_zip", models.CharField(blank=True, max_length=160)),
                ("last_query", models.CharField(blank=True, max_length=255)),
                ("last_source", models.CharField(default="search_result", max_length=40)),
                ("hit_count", models.PositiveIntegerField(default=0)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-last_seen_at"],
                "indexes": [
                    models.Index(fields=["parcel_number"], name="taxtool_par_parcel__ffba79_idx"),
                    models.Index(fields=["last_seen_at"], name="taxtool_par_last_se_8f9ffd_idx"),
                ],
            },
        ),
    ]