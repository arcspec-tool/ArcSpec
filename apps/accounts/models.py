from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.keys import PublicKeyModel


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('An email address is required.')
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.update(system_role='admin', is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra_fields)


class User(PublicKeyModel, AbstractUser):

    SYSTEM_ROLE_CHOICES = [
        ('viewer', _('Viewer')),
        ('user', _('User')),
        ('admin', _('Administrator')),
    ]

    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    system_role = models.CharField(max_length=10, choices=SYSTEM_ROLE_CHOICES, default='user')
    avatar_color = models.CharField(max_length=7, default='#284E8A')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['system_role']),
        ]

    def __str__(self):
        return self.display_name or self.get_full_name() or self.email

    @property
    def is_system_admin(self):
        return self.system_role == 'admin'

    @property
    def is_viewer(self):
        return self.system_role == 'viewer'

    def get_initials(self):
        first = self.first_name[:1].upper() if self.first_name else ''
        last = self.last_name[:1].upper() if self.last_name else ''
        return f"{first}{last}" or self.email[:2].upper()


class UserSettings(models.Model):

    PAPER_SIZE_CHOICES = [('a4', _('A4')), ('letter', _('Letter')), ('legal', _('Legal'))]
    ORIENTATION_CHOICES = [('portrait', _('Portrait')), ('landscape', _('Landscape'))]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')

    notify_project_updates = models.BooleanField(default=True)
    notify_comments = models.BooleanField(default=True)
    notify_status_changes = models.BooleanField(default=True)
    notify_collaborator_changes = models.BooleanField(default=False)
    notify_weekly_digest = models.BooleanField(default=False)

    export_paper_size = models.CharField(max_length=10, choices=PAPER_SIZE_CHOICES, default='a4')
    export_orientation = models.CharField(max_length=10, choices=ORIENTATION_CHOICES, default='portrait')
    export_include_toc = models.BooleanField(default=True)
    export_include_attributes = models.BooleanField(default=True)
    export_include_comments = models.BooleanField(default=False)
    export_include_links = models.BooleanField(default=True)

    def __str__(self):
        return f"Settings for {self.user}"
