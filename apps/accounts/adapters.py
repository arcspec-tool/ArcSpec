import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthError
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from apps.accounts.auth_methods import current
from apps.accounts.models import User

logger = logging.getLogger(__name__)

NAME_FIELDS = (('first_name', 'givenName'), ('last_name', 'surname'))


class AccountAdapter(DefaultAccountAdapter):

    def respond_user_inactive(self, request, user):
        messages.error(request, _('Your account has been deactivated. Contact a system administrator.'))
        return redirect('/')


class InviteOnlySocialAccountAdapter(DefaultSocialAccountAdapter):

    def is_open_for_signup(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('mail') or sociallogin.account.extra_data.get('email', '')
        return User.objects.filter(email__iexact=email).exists() if email else False

    def pre_social_login(self, request, sociallogin):
        if not current().entra:
            messages.error(request, _('Microsoft sign-in is turned off.'))
            raise ImmediateHttpResponse(redirect('/'))

        email = sociallogin.account.extra_data.get('mail') or sociallogin.account.extra_data.get('email', '')
        logger.info('Entra ID login attempt for email: %s', email)
        logger.info('Extra data keys: %s', list(sociallogin.account.extra_data.keys()))

        if not email:
            messages.error(request, _('Could not retrieve email from Microsoft account.'))
            raise ImmediateHttpResponse(redirect('/'))

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.error(request, _('Your account has not been invited. Contact a system administrator.'))
            raise ImmediateHttpResponse(redirect('/'))
        except User.MultipleObjectsReturned:
            logger.error('Multiple users found for email %s - possible case-variant duplicates', email)
            messages.error(request, _('A configuration error prevents login. Contact a system administrator.'))
            raise ImmediateHttpResponse(redirect('/'))

        if not user.is_active:
            messages.error(request, _('Your account has been deactivated. Contact a system administrator.'))
            raise ImmediateHttpResponse(redirect('/'))

        if not sociallogin.is_existing:
            sociallogin.connect(request, user)

        self.update_names(user, sociallogin.account.extra_data)

    @staticmethod
    def update_names(user, extra):
        changed = []
        for field, key in NAME_FIELDS:
            value = extra.get(key) or ''
            if value and getattr(user, field) != value:
                setattr(user, field, value)
                changed.append(field)
        display = extra.get('displayName') or ''
        if display and not user.display_name:
            user.display_name = display
            changed.append('display_name')
        if changed:
            user.save(update_fields=changed)

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        if error == AuthError.CANCELLED:
            messages.error(request, _('Microsoft sign-in was cancelled.'))
        else:
            logger.error('Microsoft sign-in failed: %s %r', error, exception)
            messages.error(request, _('Microsoft sign-in failed. Try again or contact a system administrator.'))
        raise ImmediateHttpResponse(redirect('/'))
