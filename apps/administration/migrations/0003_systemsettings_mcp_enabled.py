from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('administration', '0002_systemsettings_captcha_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='mcp_enabled',
            field=models.BooleanField(default=False),
        ),
    ]
