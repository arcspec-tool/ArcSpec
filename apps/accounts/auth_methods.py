from typing import NamedTuple

from django.conf import settings
from django.utils.translation import gettext as _

from apps.administration.models import SystemSettings


class AuthMethods(NamedTuple):
    entra: bool
    password: bool


def entra_configured():
    app = settings.SOCIALACCOUNT_PROVIDERS['microsoft']['APPS'][0]
    return bool(app.get('client_id') and app.get('secret') and app.get('settings', {}).get('tenant'))


def current(stored=None):
    stored = stored or SystemSettings.load()
    return AuthMethods(
        entra=bool(stored.entra_login_enabled and entra_configured()),
        password=bool(stored.password_login_enabled),
    )


def can_change_password(user):
    return current().password and user.has_usable_password()


def validate(entra, password):
    errors = []
    if not entra and not password:
        errors.append(_('At least one sign-in method must stay on.'))
    if entra and not entra_configured():
        errors.append(_('Microsoft sign-in cannot be turned on: it is not configured in this environment.'))
    return errors
