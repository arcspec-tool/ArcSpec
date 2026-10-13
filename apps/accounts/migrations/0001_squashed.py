import apps.core.keys
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True


    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('display_name', models.CharField(blank=True, max_length=150)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('location', models.CharField(blank=True, max_length=100)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('system_role', models.CharField(choices=[('viewer', 'Viewer'), ('user', 'User'), ('admin', 'Administrator')], default='user', max_length=10)),
                ('avatar_color', models.CharField(default='#284E8A', max_length=7)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'ordering': ['last_name', 'first_name'],
            },
        ),
        migrations.CreateModel(
            name='UserSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notify_project_updates', models.BooleanField(default=True)),
                ('notify_comments', models.BooleanField(default=True)),
                ('notify_status_changes', models.BooleanField(default=True)),
                ('notify_collaborator_changes', models.BooleanField(default=False)),
                ('notify_weekly_digest', models.BooleanField(default=False)),
                ('export_paper_size', models.CharField(choices=[('a4', 'A4'), ('letter', 'Letter'), ('legal', 'Legal')], default='a4', max_length=10)),
                ('export_orientation', models.CharField(choices=[('portrait', 'Portrait'), ('landscape', 'Landscape')], default='portrait', max_length=10)),
                ('export_include_toc', models.BooleanField(default=True)),
                ('export_include_attributes', models.BooleanField(default=True)),
                ('export_include_comments', models.BooleanField(default=False)),
                ('export_include_links', models.BooleanField(default=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='settings', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['system_role'], name='accounts_us_system__3174c9_idx'),
        ),
    ]
