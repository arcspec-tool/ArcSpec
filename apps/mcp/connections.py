from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from oauth2_provider.models import RefreshToken

from apps.mcp.models import Connection, TokenFamily

LAST_USED_INTERVAL = timedelta(minutes=5)


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
