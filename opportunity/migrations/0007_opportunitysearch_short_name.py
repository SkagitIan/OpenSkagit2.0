from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opportunity", "0006_notification_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunitysearch",
            name="short_name",
            field=models.TextField(blank=True),
        ),
    ]
