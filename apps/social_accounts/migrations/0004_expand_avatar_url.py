from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social_accounts", "0003_add_instagram_personal_platform"),
    ]

    operations = [
        migrations.AlterField(
            model_name="socialaccount",
            name="avatar_url",
            field=models.URLField(blank=True, default="", max_length=4096),
        ),
    ]
