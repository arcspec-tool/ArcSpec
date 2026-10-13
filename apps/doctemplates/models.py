from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.keys import PublicKeyModel


class TemplateQuerySet(models.QuerySet):

    def visible_to(self, user):
        signed_in = user is not None and user.is_authenticated
        if signed_in and user.is_system_admin:
            return self.all()
        visible = Q(is_builtin=True) | Q(is_global=True)
        if signed_in:
            visible |= Q(created_by=user)
        return self.filter(visible)


class Template(PublicKeyModel):

    DOC_TYPE_CHOICES = [
        ('requirements', _('Requirements')),
        ('architecture', _('Architecture')),
        ('testcases', _('Test Cases')),
        ('risk', _('Risk Analysis')),
        ('custom', _('Custom')),
    ]

    DOC_TYPE_PREFIX_MAP = {
        'requirements': 'REQ-',
        'architecture': 'ARC-',
        'testcases': 'TC-',
        'risk': 'RSK-',
        'custom': 'ITEM-',
    }

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='requirements')
    is_builtin = models.BooleanField(default=False)
    is_global = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_templates'
    )
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TemplateQuerySet.as_manager()

    class Meta:
        ordering = ['-is_builtin', 'display_order', 'name']

    def __str__(self):
        return self.name

    @property
    def item_id_prefix(self):
        return self.DOC_TYPE_PREFIX_MAP.get(self.doc_type, 'ITEM-')

    @property
    def section_count(self):
        return self.sections.count()


class TemplateSection(models.Model):

    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='sections')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    number = models.CharField(max_length=20)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = [('template', 'number')]

    def __str__(self):
        return f"{self.number} {self.title}"


class TemplateAttribute(models.Model):

    FIELD_TYPE_CHOICES = [
        ('text', _('Text')),
        ('number', _('Number')),
        ('date', _('Date')),
        ('boolean', _('Boolean')),
        ('user', _('User')),
        ('dropdown', _('Dropdown')),
        ('multiselect', _('Multi-select')),
    ]

    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES)
    options = models.JSONField(default=list, blank=True)
    is_builtin = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = [('template', 'name')]

    def __str__(self):
        return f"{self.name} ({self.field_type})"
