from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0007_drop_levy_area_map")]

    operations = [
        migrations.CreateModel(
            name="HouseContentEpisode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("episode_id", models.SlugField(max_length=100, unique=True)),
                ("title", models.TextField()),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("prepared", "Prepared"), ("rendering", "Rendering"), ("ready", "Ready"), ("failed", "Failed")], default="prepared", max_length=20)),
                ("aspect_ratio", models.CharField(blank=True, max_length=10)),
                ("width", models.PositiveIntegerField(blank=True, null=True)),
                ("height", models.PositiveIntegerField(blank=True, null=True)),
                ("duration", models.FloatField(blank=True, null=True)),
                ("cloudinary_public_id", models.TextField(blank=True)),
                ("video_url", models.URLField(blank=True, max_length=1000)),
                ("thumbnail_url", models.URLField(blank=True, max_length=1000)),
                ("manifest", models.JSONField(blank=True, default=dict)),
                ("qa_results", models.JSONField(blank=True, default=dict)),
                ("warnings", models.JSONField(blank=True, default=list)),
                ("failure_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddIndex(
            model_name="housecontentepisode",
            index=models.Index(fields=["status", "updated_at"], name="core_housec_status_ed8287_idx"),
        ),
    ]
