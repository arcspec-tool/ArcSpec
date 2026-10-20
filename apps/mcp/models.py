from django.conf import settings
from django.db import models
from django.utils import timezone
from oauth2_provider.settings import oauth2_settings

from apps.core.keys import PublicKeyModel


class Connection(PublicKeyModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mcp_connections')
    application = models.ForeignKey(oauth2_settings.APPLICATION_MODEL, on_delete=models.CASCADE, related_name='mcp_connections')
    scope = models.CharField(max_length=50)
    connected_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'application'], name='mcp_connection_user_application'),
        ]


class TokenFamily(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name='token_families')
    token_family = models.UUIDField(unique=True)
    authorized_at = models.DateTimeField(default=timezone.now)
