import apps.core.keys
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

TAG_PRESETS = [
    ('Security', '#dc2626'),
    ('Performance', '#d97706'),
    ('UX', '#7c3aed'),
    ('API', '#0891b2'),
    ('Database', '#16a34a'),
    ('Compliance', '#be185d'),
    ('MVP', '#284E8A'),
    ('Technical Debt', '#64748b'),
    ('Blocked', '#ef4444'),
    ('Needs Discussion', '#f59e0b'),
]


def create_tag_presets(apps, schema_editor):
    Tag = apps.get_model('projects', 'Tag')
    for name, color in TAG_PRESETS:
        Tag.objects.get_or_create(name=name, project=None, is_preset=True, defaults={'color': color})


class Migration(migrations.Migration):

    initial = True


    dependencies = [
        ('doctemplates', '0001_squashed'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('item_id', models.CharField(db_index=True, max_length=20)),
                ('text', models.TextField()),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('in-review', 'In Review'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='draft', max_length=20)),
                ('priority', models.CharField(choices=[('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], default='medium', max_length=20)),
                ('order', models.PositiveIntegerField(default=0)),
                ('image', models.ImageField(blank=True, null=True, upload_to='items/images/%Y/%m/')),
                ('image_caption', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assignee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_items', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_items', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('file', models.FileField(upload_to='attachments/%Y/%m/')),
                ('filename', models.CharField(max_length=255)),
                ('file_size', models.PositiveIntegerField()),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='projects.item')),
            ],
            options={
                'ordering': ['-uploaded_at'],
            },
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('slug', models.SlugField(max_length=200, unique=True)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('in-review', 'In Review'), ('draft', 'Draft'), ('archived', 'Archived')], default='draft', max_length=20)),
                ('color', models.CharField(default='#073378', max_length=7)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('archived_at', models.DateTimeField(blank=True, null=True)),
                ('next_item_number', models.PositiveIntegerField(default=1)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_projects', to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='doctemplates.template')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddField(
            model_name='item',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='projects.project'),
        ),
        migrations.CreateModel(
            name='ProjectAttribute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('field_type', models.CharField(choices=[('text', 'Text'), ('number', 'Number'), ('date', 'Date'), ('boolean', 'Boolean'), ('user', 'User'), ('dropdown', 'Dropdown'), ('multiselect', 'Multi-select')], max_length=20)),
                ('options', models.JSONField(blank=True, default=list)),
                ('is_builtin', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attributes', to='projects.project')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='ItemAttributeValue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.TextField(blank=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attribute_values', to='projects.item')),
                ('attribute', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='values', to='projects.projectattribute')),
            ],
        ),
        migrations.CreateModel(
            name='ProjectMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('role', models.CharField(choices=[('admin', 'Admin'), ('editor', 'Editor'), ('viewer', 'Viewer')], max_length=20)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('preferences', models.JSONField(blank=True, default=dict)),
                ('added_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invited_memberships', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_memberships', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ProjectVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('version_number', models.CharField(max_length=10)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('change_summary', models.CharField(blank=True, max_length=200)),
                ('item_count', models.PositiveIntegerField(default=0)),
                ('snapshot', models.JSONField(blank=True, default=dict)),
                ('changed_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='projects.project')),
            ],
            options={
                'ordering': ['-changed_at'],
            },
        ),
        migrations.CreateModel(
            name='SavedView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('filters', models.JSONField(default=dict)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_views', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_views', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-is_default', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Section',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('number', models.CharField(max_length=20)),
                ('order', models.PositiveIntegerField(default=0)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='projects.section')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='projects.project')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.AddField(
            model_name='item',
            name='section',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='projects.section'),
        ),
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('name', models.CharField(max_length=50)),
                ('color', models.CharField(default='#64748b', max_length=7)),
                ('is_preset', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tags', to='projects.project')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ItemTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='item_tags', to='projects.item')),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='item_tags', to='projects.tag')),
            ],
        ),
        migrations.CreateModel(
            name='TraceabilityLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('link_type', models.CharField(choices=[('traces-to', 'Traces to'), ('derived-from', 'Derived from'), ('verified-by', 'Verified by'), ('conflicts-with', 'Conflicts with'), ('related-to', 'Related to')], max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('source_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outgoing_links', to='projects.item')),
                ('target_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_links', to='projects.item')),
            ],
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_key', models.UUIDField(default=apps.core.keys.uuid7, editable=False, unique=True)),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='comments', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='replies', to='projects.comment')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='projects.item')),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['item', 'created_at'], name='projects_co_item_id_be5b54_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['status'], name='projects_pr_status_f023cb_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['slug'], name='projects_pr_slug_042165_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['-updated_at'], name='projects_pr_updated_bf89a6_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='projectattribute',
            unique_together={('project', 'name')},
        ),
        migrations.AlterUniqueTogether(
            name='itemattributevalue',
            unique_together={('item', 'attribute')},
        ),
        migrations.AddIndex(
            model_name='projectmembership',
            index=models.Index(fields=['project', 'user'], name='projects_pr_project_710ab3_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='projectmembership',
            unique_together={('project', 'user')},
        ),
        migrations.AddIndex(
            model_name='projectversion',
            index=models.Index(fields=['project', '-changed_at'], name='projects_pr_project_7ae098_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='savedview',
            unique_together={('project', 'user', 'name')},
        ),
        migrations.AddIndex(
            model_name='section',
            index=models.Index(fields=['project', 'order'], name='projects_se_project_1629a6_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['project', 'section', 'order'], name='projects_it_project_373ef6_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['project', 'item_id'], name='projects_it_project_323af7_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['status'], name='projects_it_status_1763c7_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['priority'], name='projects_it_priorit_1954db_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['assignee'], name='projects_it_assigne_1c43a6_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='item',
            unique_together={('project', 'item_id')},
        ),
        migrations.AlterUniqueTogether(
            name='tag',
            unique_together={('name', 'project')},
        ),
        migrations.AlterUniqueTogether(
            name='itemtag',
            unique_together={('item', 'tag')},
        ),
        migrations.AddIndex(
            model_name='traceabilitylink',
            index=models.Index(fields=['source_item'], name='projects_tr_source__42bb9e_idx'),
        ),
        migrations.AddIndex(
            model_name='traceabilitylink',
            index=models.Index(fields=['target_item'], name='projects_tr_target__ac337c_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='traceabilitylink',
            unique_together={('source_item', 'target_item', 'link_type')},
        ),
        migrations.RunPython(create_tag_presets, migrations.RunPython.noop),
    ]
