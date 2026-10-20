from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from oauth2_provider.models import AccessToken, Grant, RefreshToken
from oauth2_provider.settings import oauth2_settings

from apps.mcp.models import Connection, TokenFamily

LAST_USED_INTERVAL = timedelta(minutes=5)


def listed(user, now):
    live = RefreshToken.objects.filter(user=user, token_family=OuterRef('token_family'), revoked__isnull=True)
    current = TokenFamily.objects.filter(
        connection=OuterRef('pk'),
        authorized_at__gt=now - timedelta(seconds=oauth2_settings.REFRESH_TOKEN_EXPIRE_SECONDS),
    ).filter(Exists(live))
    return Connection.objects.filter(user=user).filter(Exists(current)).select_related('application').order_by('-connected_at')


def disconnect(connection):
    tokens = {'user': connection.user, 'application': connection.application}
    with transaction.atomic():
        families = set(RefreshToken.objects.filter(revoked__isnull=True, **tokens).values_list('token_family', flat=True))
        for family in families - {None}:
            RefreshToken.revoke_family(family)
        for token in RefreshToken.objects.filter(token_family__isnull=True, revoked__isnull=True, **tokens):
            token.revoke()
        AccessToken.objects.filter(**tokens).delete()
        Grant.objects.filter(**tokens).delete()
        connection.delete()


def record_authorization(sender, request, token, **kwargs):
    if request.POST.get('grant_type') != 'authorization_code':
        return
    with transaction.atomic():
        connection, created = Connection.objects.get_or_create(
            user=token.user, application=token.application, defaults={'scope': token.scope},
        )
        if not created and connection.scope != token.scope:
            connection.scope = token.scope
            connection.save(update_fields=['scope'])
        TokenFamily.objects.create(connection=connection, token_family=token.refresh_token.token_family)
        live = RefreshToken.objects.filter(user=token.user, application=token.application, revoked__isnull=True)
        connection.token_families.exclude(token_family__in=live.values('token_family')).delete()


def touch(user, application, now):
    stale = Q(last_used_at__isnull=True) | Q(last_used_at__lt=now - LAST_USED_INTERVAL)
    Connection.objects.filter(stale, user=user, application=application).update(last_used_at=now)
