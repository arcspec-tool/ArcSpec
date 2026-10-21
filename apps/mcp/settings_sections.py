from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.settings_sections import register
from apps.mcp import auth, connections


@register('connected_apps', 'mcp/settings/_connected_apps.html')
def connected_apps(request):
    rows = [
        {
            'public_key': connection.public_key,
            'name': connection.application.name or _('Unnamed app'),
            'host': urlsplit(connection.application.client_id).hostname,
            'write': 'write' in connection.scope.split(),
            'connected_at': connection.connected_at,
            'last_used_at': connection.last_used_at,
        }
        for connection in connections.listed(request.user, timezone.now())
    ]
    enabled = auth.mcp_enabled()
    if not enabled and not rows:
        return None
    return {'connections': rows, 'mcp_enabled': enabled}
