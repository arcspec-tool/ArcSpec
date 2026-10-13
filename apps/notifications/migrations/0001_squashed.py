import apps.core.keys
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True


    dependencies = [
        ('projects', '0001_squashed'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('created', 'Created'), ('updated', 'Updated'), ('edited', 'Edited'), ('deleted', 'Deleted'), ('status_changed', 'Status Changed'), ('priority_changed', 'Priority Changed'), ('commented', 'Commented'), ('exported', 'Exported'), ('collaborator_added', 'Collaborator Added'), ('collaborator_removed', 'Collaborator Removed'), ('collaborator_role_changed', 'Collaborator Role Changed'), ('tag_added', 'Tag Added'), ('tag_removed', 'Tag Removed'), ('attachment_added', 'Attachment Added'), ('attachment_removed', 'Attachment Removed'), ('link_added', 'Link Added'), ('link_removed', 'Link Removed'), ('version_restored', 'Version Restored'), ('bulk_updated', 'Bulk Updated'), ('duplicated', 'Duplicated'), ('archived', 'Archived'), ('restored', 'Restored')], max_length=50)),
                ('target_type', models.CharField(max_length=50)),
                ('target_id', models.CharField(max_length=50)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['project', '-created_at'], name='notificatio_project_7fa6f8_idx'), models.Index(fields=['project', 'action'], name='notificatio_project_5f41f2_idx'), models.Index(fields=['user'], name='notificatio_user_id_946082_idx')],
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('type', models.CharField(choices=[('item_created', 'Item Created'), ('comment', 'Comment'), ('collaborator_added', 'Collaborator Added'), ('review_requested', 'Review Requested'), ('status_changed', 'Status Changed'), ('mention', 'Mention')], max_length=50)),
                ('message', models.TextField()),
                ('link', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('pushed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', 'is_read', '-created_at'], name='notificatio_user_id_f2ad08_idx'), models.Index(fields=['user', '-created_at'], name='notificatio_user_id_05b4bc_idx')],
            },
        ),
    ]
