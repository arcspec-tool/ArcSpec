from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.keys import PublicKeyModel


class AuditLog(models.Model):

    ACTION_CHOICES = [
        ('created', _('Created')),
        ('updated', _('Updated')),
        ('edited', _('Edited')),
        ('deleted', _('Deleted')),
        ('status_changed', _('Status Changed')),
        ('priority_changed', _('Priority Changed')),
        ('commented', _('Commented')),
        ('exported', _('Exported')),
        ('collaborator_added', _('Collaborator Added')),
        ('collaborator_removed', _('Collaborator Removed')),
        ('collaborator_role_changed', _('Collaborator Role Changed')),
        ('tag_added', _('Tag Added')),
        ('tag_removed', _('Tag Removed')),
        ('attachment_added', _('Attachment Added')),
        ('attachment_removed', _('Attachment Removed')),
        ('link_added', _('Link Added')),
        ('link_removed', _('Link Removed')),
        ('version_restored', _('Version Restored')),
        ('bulk_updated', _('Bulk Updated')),
        ('duplicated', _('Duplicated')),
        ('archived', _('Archived')),
        ('restored', _('Restored')),
    ]

    ACTION_ICONS = {
        'created': ('bi-plus-circle', 'text-primary'),
        'updated': ('bi-pencil', 'text-warning'),
        'edited': ('bi-pencil-square', 'text-warning'),
        'deleted': ('bi-trash', 'text-danger'),
        'status_changed': ('bi-check-circle', 'text-success'),
        'commented': ('bi-chat-dots', 'text-info'),
        'collaborator_added': ('bi-person-plus', 'text-secondary'),
        'collaborator_removed': ('bi-person-dash', 'text-secondary'),
        'exported': ('bi-download', 'text-primary'),
        'priority_changed': ('bi-arrow-down-up', 'text-warning'),
        'tag_added': ('bi-tag', 'text-info'),
        'tag_removed': ('bi-tag', 'text-muted'),
        'attachment_added': ('bi-paperclip', 'text-success'),
        'attachment_removed': ('bi-paperclip', 'text-danger'),
        'link_added': ('bi-link-45deg', 'text-primary'),
        'link_removed': ('bi-link-45deg', 'text-danger'),
        'duplicated': ('bi-files', 'text-primary'),
        'bulk_updated': ('bi-collection', 'text-warning'),
        'version_restored': ('bi-clock-history', 'text-info'),
        'archived': ('bi-archive', 'text-secondary'),
        'restored': ('bi-arrow-counterclockwise', 'text-success'),
    }

    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=50)
    target_id = models.CharField(max_length=50)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['project', 'action']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user} {self.action} {self.target_type} {self.target_id}"


class Notification(PublicKeyModel):

    TYPE_CHOICES = [
        ('item_created', _('Item Created')),
        ('comment', _('Comment')),
        ('collaborator_added', _('Collaborator Added')),
        ('review_requested', _('Review Requested')),
        ('status_changed', _('Status Changed')),
        ('mention', _('Mention')),
    ]

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    pushed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"Notification for {self.user}: {self.message[:50]}"
