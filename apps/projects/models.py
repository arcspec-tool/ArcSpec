from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core.keys import PublicKeyModel


class ProjectQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status='active')

    def for_user(self, user):
        if user.is_system_admin:
            return self.all()
        return self.filter(memberships__user=user)

    def archived(self):
        return self.filter(status='archived')


class Project(models.Model):

    STATUS_CHOICES = [
        ('active', gettext_lazy('Active')),
        ('in-review', gettext_lazy('In Review')),
        ('draft', gettext_lazy('Draft')),
        ('archived', gettext_lazy('Archived')),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    template = models.ForeignKey('doctemplates.Template', on_delete=models.PROTECT, related_name='projects')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    color = models.CharField(max_length=7, default='#073378')
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='owned_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    next_item_number = models.PositiveIntegerField(default=1)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['slug']),
            models.Index(fields=['-updated_at']),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('project_detail', kwargs={'slug': self.slug})

    def copy_template_structure(self):
        sections = {}
        for template_section in self.template.sections.order_by('order'):
            sections[template_section.pk] = Section.objects.create(
                project=self,
                title=template_section.title,
                description=template_section.description,
                number=template_section.number,
                order=template_section.order,
                parent=sections.get(template_section.parent_id),
            )
        for template_attribute in self.template.attributes.order_by('order'):
            ProjectAttribute.objects.create(
                project=self,
                name=template_attribute.name,
                field_type=template_attribute.field_type,
                options=template_attribute.options,
                is_builtin=template_attribute.is_builtin,
                order=template_attribute.order,
            )

    def generate_item_id(self):
        prefix = self.template.item_id_prefix
        item_id = f"{prefix}{self.next_item_number:03d}"
        return item_id

    @property
    def item_count(self):
        return self.items.count()

    @property
    def collaborator_count(self):
        return self.memberships.count()

    def get_user_role(self, user):
        if user.is_system_admin:
            return 'admin'
        try:
            return self.memberships.get(user=user).role
        except ProjectMembership.DoesNotExist:
            return None

    @staticmethod
    def generate_unique_slug(name):
        slug = slugify(name)
        if not Project.objects.filter(slug=slug).exists():
            return slug
        counter = 2
        while Project.objects.filter(slug=f'{slug}-{counter}').exists():
            counter += 1
        return f'{slug}-{counter}'


class ProjectMembership(PublicKeyModel):

    ROLE_CHOICES = [
        ('admin', gettext_lazy('Admin')),
        ('editor', gettext_lazy('Editor')),
        ('viewer', gettext_lazy('Viewer')),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invited_memberships'
    )
    preferences = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [('project', 'user')]
        indexes = [
            models.Index(fields=['project', 'user']),
        ]

    def __str__(self):
        return f"{self.user} - {self.role} on {self.project}"


class Section(PublicKeyModel):

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sections')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    number = models.CharField(max_length=20)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['project', 'order']),
        ]

    def __str__(self):
        return f"{self.number} {self.title}"

    @property
    def item_count(self):
        return self.items.count()


class ItemQuerySet(models.QuerySet):
    def active(self):
        return self.all()

    def by_status(self, status):
        return self.filter(status=status)

    def by_priority(self, priority):
        return self.filter(priority=priority)

    def search(self, query):
        return self.filter(
            Q(item_id__icontains=query) |
            Q(text__icontains=query)
        )


class Item(PublicKeyModel):

    STATUS_CHOICES = [
        ('draft', gettext_lazy('Draft')),
        ('in-review', gettext_lazy('In Review')),
        ('approved', gettext_lazy('Approved')),
        ('rejected', gettext_lazy('Rejected')),
    ]

    PRIORITY_CHOICES = [
        ('high', gettext_lazy('High')),
        ('medium', gettext_lazy('Medium')),
        ('low', gettext_lazy('Low')),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='items')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='items')
    item_id = models.CharField(max_length=20, db_index=True)
    text = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    assignee = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_items'
    )
    order = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='items/images/%Y/%m/', blank=True, null=True)
    image_caption = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='created_items')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ItemQuerySet.as_manager()

    class Meta:
        ordering = ['order']
        unique_together = [('project', 'item_id')]
        indexes = [
            models.Index(fields=['project', 'section', 'order']),
            models.Index(fields=['project', 'item_id']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['assignee']),
        ]

    def __str__(self):
        return f"{self.item_id}: {self.text[:50]}"


class ProjectAttribute(PublicKeyModel):

    FIELD_TYPE_CHOICES = [
        ('text', gettext_lazy('Text')),
        ('number', gettext_lazy('Number')),
        ('date', gettext_lazy('Date')),
        ('boolean', gettext_lazy('Boolean')),
        ('user', gettext_lazy('User')),
        ('dropdown', gettext_lazy('Dropdown')),
        ('multiselect', gettext_lazy('Multi-select')),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES)
    options = models.JSONField(default=list, blank=True)
    is_builtin = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = [('project', 'name')]

    def __str__(self):
        return f"{self.name} ({self.field_type})"

    def display_value(self, value, user_names=None):
        if self.field_type == 'boolean':
            return _('Yes') if value == 'true' else _('No')
        if self.field_type == 'user' and value:
            if user_names is None:
                user_names = attribute_user_names(self.project)
            return user_names.get(str(value), str(value))
        return value or ''


def attribute_user_names(project):
    ids = set()
    values = ItemAttributeValue.objects.filter(
        attribute__project=project, attribute__field_type='user'
    ).values_list('value', flat=True)
    for value in values:
        if value.isdigit():
            ids.add(int(value))
    if not ids:
        return {}
    User = get_user_model()
    return {str(user.pk): str(user) for user in User.objects.filter(pk__in=ids)}


class ItemAttributeValue(models.Model):

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='attribute_values')
    attribute = models.ForeignKey(
        ProjectAttribute, on_delete=models.CASCADE, related_name='values'
    )
    value = models.TextField(blank=True)

    class Meta:
        unique_together = [('item', 'attribute')]

    def __str__(self):
        return f"{self.attribute.name}={self.value} for {self.item.item_id}"


class Tag(PublicKeyModel):

    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#64748b')
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, null=True, blank=True, related_name='tags'
    )
    is_preset = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('name', 'project')]
        ordering = ['name']

    def __str__(self):
        return self.name

    @staticmethod
    def for_project(project):
        return Tag.objects.filter(
            Q(project__isnull=True, is_preset=True) | Q(project=project)
        )


class ItemTag(models.Model):

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='item_tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='item_tags')

    class Meta:
        unique_together = [('item', 'tag')]

    def __str__(self):
        return f"{self.item.item_id} tagged {self.tag.name}"


class Attachment(PublicKeyModel):

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/')
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.filename

    @property
    def file_size_display(self):
        if self.file_size < 1024:
            return _('%(size)s B') % {'size': self.file_size}
        elif self.file_size < 1024 * 1024:
            return _('%(size)s KB') % {'size': f'{self.file_size / 1024:.1f}'}
        return _('%(size)s MB') % {'size': f'{self.file_size / (1024 * 1024):.1f}'}

    @property
    def file_type_icon(self):
        ext = self.filename.rsplit('.', 1)[-1].lower() if '.' in self.filename else ''
        icons = {
            'pdf': 'bi-file-earmark-pdf text-danger',
            'doc': 'bi-file-earmark-word text-primary',
            'docx': 'bi-file-earmark-word text-primary',
            'png': 'bi-file-earmark-image text-success',
            'jpg': 'bi-file-earmark-image text-success',
            'jpeg': 'bi-file-earmark-image text-success',
            'gif': 'bi-file-earmark-image text-success',
        }
        return icons.get(ext, 'bi-file-earmark text-muted')


class TraceabilityLink(PublicKeyModel):

    LINK_TYPE_CHOICES = [
        ('traces-to', gettext_lazy('Traces to')),
        ('derived-from', gettext_lazy('Derived from')),
        ('verified-by', gettext_lazy('Verified by')),
        ('conflicts-with', gettext_lazy('Conflicts with')),
        ('related-to', gettext_lazy('Related to')),
    ]

    LINK_TYPE_ICONS = {
        'traces-to': ('bi-arrow-right-short', 'text-primary'),
        'derived-from': ('bi-arrow-left-short', 'text-info'),
        'verified-by': ('bi-check2-square', 'text-success'),
        'conflicts-with': ('bi-exclamation-diamond', 'text-danger'),
        'related-to': ('bi-link-45deg', 'text-secondary'),
    }

    source_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='outgoing_links')
    target_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='incoming_links')
    link_type = models.CharField(max_length=30, choices=LINK_TYPE_CHOICES)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('source_item', 'target_item', 'link_type')]
        indexes = [
            models.Index(fields=['source_item']),
            models.Index(fields=['target_item']),
        ]

    def __str__(self):
        return f"{self.source_item.item_id} -{self.link_type}-> {self.target_item.item_id}"


class Comment(PublicKeyModel):

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='comments')
    text = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['item', 'created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.author} on {self.item.item_id}"


class ProjectVersion(PublicKeyModel):

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='versions')
    version_number = models.CharField(max_length=10)
    changed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)
    change_summary = models.CharField(max_length=200, blank=True)
    item_count = models.PositiveIntegerField(default=0)
    snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['project', '-changed_at']),
        ]

    def __str__(self):
        return f"{self.project.name} v{self.version_number}"


class SavedView(PublicKeyModel):

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='saved_views')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='saved_views')
    name = models.CharField(max_length=100)
    filters = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', 'name']
        unique_together = [('project', 'user', 'name')]

    def __str__(self):
        return f"{self.name} ({self.project.name})"
