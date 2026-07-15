from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("opportunity", "0008_public_intelligence_example"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="publicintelligenceexample",
            new_name="opp_pub_active_sort_idx",
            old_name="opportunity_public_is_active_8f72d0_idx",
        ),
        migrations.RenameIndex(
            model_name="publicintelligenceexample",
            new_name="opp_pub_status_idx",
            old_name="opportunity_public_status_0e0b3a_idx",
        ),
    ]
