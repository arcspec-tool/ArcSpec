import apps.core.keys
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        migrations.swappable_dependency(settings.OAUTH2_PROVIDER_APPLICATION_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Connection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('scope', models.CharField(max_length=50)),
                ('connected_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mcp_connections', to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mcp_connections', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='TokenFamily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_family', models.UUIDField(unique=True)),
                ('authorized_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('connection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='token_families', to='mcp.connection')),
            ],
        ),
        migrations.AddConstraint(
            model_name='connection',
            constraint=models.UniqueConstraint(fields=('user', 'application'), name='mcp_connection_user_application'),
        ),
    ]
