from django.db import models
from django.utils.translation import gettext_lazy as _


class SystemSettings(models.Model):

    org_name = models.CharField(max_length=200, default='ArcSpec')
    max_attachment_size_mb = models.PositiveIntegerField(default=10)
    auto_archive_enabled = models.BooleanField(default=False)
    auto_archive_days = models.PositiveIntegerField(default=90)
    allow_user_restore = models.BooleanField(default=True)
    auto_delete_archived = models.BooleanField(default=False)
    auto_delete_days = models.PositiveIntegerField(default=365)
    entra_login_enabled = models.BooleanField(default=True)
    password_login_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('System Settings')
        verbose_name_plural = _('System Settings')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(entra_login_enabled=True) | models.Q(password_login_enabled=True),
                name='administration_one_sign_in_method_on',
                violation_error_message=_('At least one sign-in method must stay on.'),
            ),
        ]

    def __str__(self):
        return 'System Settings'

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
