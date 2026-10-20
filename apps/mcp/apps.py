from django.apps import AppConfig
from django.db.models.signals import pre_save
from oauth2_provider.signals import app_authorized


class McpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mcp'
    label = 'mcp'

    def ready(self):
        from apps.mcp.connections import record_authorization
        from apps.mcp.limits import limit_email
        from apps.notifications.models import Notification
        app_authorized.connect(record_authorization, dispatch_uid='mcp_record_authorization')
        pre_save.connect(limit_email, sender=Notification, dispatch_uid='mcp_limit_email')
