import hashlib
import json
from contextvars import ContextVar

from django.conf import settings
from django.utils import timezone
from mcp.server.auth.provider import AccessToken as GrantedToken
from oauth2_provider.models import AccessToken

from apps.administration.models import SystemSettings
from apps.mcp import connections

SCOPES = ('read', 'write')
WRITE_TOOLS = ('create_item', 'create_items', 'update_item', 'set_item_tags', 'add_comment', 'add_link')

current_token = ContextVar('mcp_current_token', default=None)


def mcp_enabled():
    return SystemSettings.load().mcp_enabled


def resource_url():
    return settings.SITE_URL + '/mcp/'


def metadata_url():
    return settings.SITE_URL + '/.well-known/oauth-protected-resource/mcp/'


def same_resource(first, second):
    return first.rstrip('/') == second.rstrip('/')


def authenticate(raw_token):
    checksum = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    token = AccessToken.objects.select_related('user', 'application').filter(token_checksum=checksum).first()
    if token is None or token.is_expired() or token.user is None or not token.user.is_active:
        return None
    wanted = resource_url()
    if not any(same_resource(str(entry), wanted) for entry in token.resource):
        return None
    granted = set(token.scope.split())
    if 'read' not in granted:
        return None
    connections.touch(token.user, token.application, timezone.now())
    return GrantedToken(
        token='',
        client_id=token.application.client_id if token.application else '',
        scopes=[scope for scope in SCOPES if scope in granted],
        expires_at=int(token.expires.timestamp()),
        resource=wanted,
        subject=str(token.user.public_key),
    )


class ContextTokenVerifier:

    async def verify_token(self, token):
        return current_token.get()


def challenge(error=None, scope='read'):
    parts = []
    if error:
        parts.append(f'error="{error}"')
    parts.append(f'resource_metadata="{metadata_url()}"')
    parts.append(f'scope="{scope}"')
    return 'Bearer ' + ', '.join(parts)


def calls_write_tool(payload):
    for message in payload if isinstance(payload, list) else [payload]:
        if not isinstance(message, dict) or message.get('method') != 'tools/call':
            continue
        params = message.get('params')
        if isinstance(params, dict) and params.get('name') in WRITE_TOOLS:
            return True
    return False


def error_body(description, error=None):
    body = {'error_description': description}
    if error:
        body['error'] = error
    return json.dumps(body).encode()
