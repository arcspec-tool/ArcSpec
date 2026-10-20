from django.apps import AppConfig
from oauth2_provider.signals import app_authorized


class McpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mcp'
    label = 'mcp'

    def ready(self):
        from apps.mcp.connections import record_authorization
        app_authorized.connect(record_authorization, dispatch_uid='mcp_record_authorization')
