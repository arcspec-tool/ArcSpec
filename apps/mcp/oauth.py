from datetime import timedelta
from urllib.parse import urlsplit

from django.urls import reverse
from django.utils import timezone
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.settings import oauth2_settings

from apps.mcp.models import TokenFamily

LOOPBACK_HOSTS = ('127.0.0.1', '::1', 'localhost')


class AuthorizeEndpointCIMDPermission:

    def has_permission(self, request, client_id):
        return urlsplit(request.uri).path == reverse('oauth2_provider:authorize')


def authorization_expired(token_family, now):
    family = TokenFamily.objects.filter(token_family=token_family).first()
    limit = timedelta(seconds=oauth2_settings.REFRESH_TOKEN_EXPIRE_SECONDS)
    return family is None or family.authorized_at + limit <= now


class MCPOAuth2Validator(OAuth2Validator):

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        parts = urlsplit(redirect_uri)
        if parts.scheme == 'http' and parts.hostname not in LOOPBACK_HOSTS:
            return False
        return super().validate_redirect_uri(client_id, redirect_uri, request, *args, **kwargs)

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        if not super().validate_refresh_token(refresh_token, client, request, *args, **kwargs):
            return False
        token = request.refresh_token_instance
        return token.user.is_active and not authorization_expired(token.token_family, timezone.now())
