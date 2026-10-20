from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('administration', '0001_squashed'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='captcha_provider',
            field=models.CharField(blank=True, choices=[('', 'Off'), ('turnstile', 'Cloudflare Turnstile'), ('hcaptcha', 'hCaptcha')], default='', max_length=20),
        ),
    ]
