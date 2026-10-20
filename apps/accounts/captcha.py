import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.administration.models import SystemSettings

logger = logging.getLogger(__name__)

VERIFY_TIMEOUT_SECONDS = 5


class Provider:
    name = ''
    script_url = ''
    widget_class = ''
    response_field = ''
    verify_url = ''
    csp = {}

    def __init__(self, site_key, secret_key):
        self.site_key = site_key
        self.secret_key = secret_key

    def widget_attrs(self):
        return {'class': self.widget_class, 'data-sitekey': self.site_key, 'data-theme': 'light'}

    def verify_data(self, token):
        return {'secret': self.secret_key, 'response': token}

    def verify(self, token):
        request = Request(self.verify_url, data=urlencode(self.verify_data(token)).encode(), method='POST')
        with urlopen(request, timeout=VERIFY_TIMEOUT_SECONDS) as response:
            return json.load(response).get('success') is True


class Turnstile(Provider):
    name = 'turnstile'
    script_url = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
    widget_class = 'cf-turnstile'
    response_field = 'cf-turnstile-response'
    verify_url = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    csp = {
        'script-src': ['https://challenges.cloudflare.com'],
        'frame-src': ['https://challenges.cloudflare.com'],
    }

    def widget_attrs(self):
        return {**super().widget_attrs(), 'data-language': settings.LANGUAGE_CODE, 'data-size': 'flexible'}


class HCaptcha(Provider):
    name = 'hcaptcha'
    widget_class = 'h-captcha'
    response_field = 'h-captcha-response'
    verify_url = 'https://api.hcaptcha.com/siteverify'
    csp = {
        directive: ['https://hcaptcha.com', 'https://*.hcaptcha.com']
        for directive in ('script-src', 'frame-src', 'style-src', 'connect-src')
    }

    @property
    def script_url(self):
        return f'https://js.hcaptcha.com/1/api.js?{urlencode({"hl": settings.LANGUAGE_CODE})}'

    def verify_data(self, token):
        return {**super().verify_data(token), 'sitekey': self.site_key}


PROVIDERS = {provider.name: provider for provider in (Turnstile, HCaptcha)}


def csp_sources():
    sources = {}
    for provider in PROVIDERS.values():
        for directive, hosts in provider.csp.items():
            sources.setdefault(directive, []).extend(hosts)
    return sources


def configured(name):
    keys = settings.CAPTCHA_KEYS.get(name, {})
    return bool(keys.get('site_key') and keys.get('secret_key'))


def active(stored=None):
    stored = stored or SystemSettings.load()
    name = stored.captcha_provider
    if not stored.password_login_enabled or not name or not configured(name):
        return None
    return PROVIDERS[name](**settings.CAPTCHA_KEYS[name])


class CaptchaWidget(forms.Widget):
    template_name = 'accounts/includes/_captcha.html'

    def __init__(self, provider):
        super().__init__(attrs=provider.widget_attrs())
        self.provider = provider

    def value_from_datadict(self, data, files, name):
        return data.get(self.provider.response_field, '')

    def use_required_attribute(self, initial):
        return False


class CaptchaField(forms.Field):
    default_error_messages = {
        'required': _('Complete the verification and try again.'),
        'invalid': _('The verification failed. Try again.'),
        'unavailable': _('The verification service could not be reached. Try again later.'),
    }

    def __init__(self, provider, **kwargs):
        self.provider = provider
        super().__init__(widget=CaptchaWidget(provider), label='', **kwargs)

    def validate(self, value):
        super().validate(value)
        try:
            passed = self.provider.verify(value)
        except (OSError, ValueError):
            logger.exception('The %s verification could not be completed', self.provider.name)
            raise ValidationError(self.error_messages['unavailable'], code='unavailable')
        if not passed:
            raise ValidationError(self.error_messages['invalid'], code='invalid')


class CaptchaFormMixin:

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.captcha_provider = active()
        if self.captcha_provider:
            self.fields['captcha'] = CaptchaField(self.captcha_provider)
