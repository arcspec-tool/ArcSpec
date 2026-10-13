from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True


    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SystemSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('org_name', models.CharField(default='ArcSpec', max_length=200)),
                ('max_attachment_size_mb', models.PositiveIntegerField(default=10)),
                ('auto_archive_enabled', models.BooleanField(default=False)),
                ('auto_archive_days', models.PositiveIntegerField(default=90)),
                ('allow_user_restore', models.BooleanField(default=True)),
                ('auto_delete_archived', models.BooleanField(default=False)),
                ('auto_delete_days', models.PositiveIntegerField(default=365)),
                ('entra_login_enabled', models.BooleanField(default=True)),
                ('password_login_enabled', models.BooleanField(default=False)),
            ],
            options={
                'verbose_name': 'System Settings',
                'verbose_name_plural': 'System Settings',
                'constraints': [models.CheckConstraint(condition=models.Q(('entra_login_enabled', True), ('password_login_enabled', True), _connector='OR'), name='administration_one_sign_in_method_on', violation_error_message='At least one sign-in method must stay on.')],
            },
        ),
    ]
