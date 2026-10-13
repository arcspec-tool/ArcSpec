from django.conf import settings
from django.test import TestCase
from django.urls import get_resolver, resolve, reverse
from django.urls.resolvers import URLResolver

from apps.accounts.views import entra_login

OAUTH2_VIEWS = 'allauth.socialaccount.providers.oauth2.views'


def allauth_views():
    found = []

    def walk(patterns, prefix):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif pattern.callback.__module__.startswith('allauth.'):
                found.append((prefix + str(pattern.pattern), pattern.name, pattern.callback.__module__))

    walk(get_resolver().url_patterns, '')
    return found


class AllauthRoutesTest(TestCase):

    def test_only_the_callback_comes_from_allauth(self):
        prefix = f'auth/callback/{settings.AUTH_CALLBACK_PREFIX}/'
        self.assertEqual(allauth_views(), [
            (f'{prefix}microsoft/login/callback/', 'microsoft_callback', OAUTH2_VIEWS),
        ])

    def test_the_microsoft_start_is_the_project_gate(self):
        self.assertIs(resolve('/auth/microsoft/').func, entra_login)
        self.assertEqual(reverse('microsoft_login'), '/auth/microsoft/')
        self.assertEqual(self.client.get(f'/auth/callback/{settings.AUTH_CALLBACK_PREFIX}/microsoft/login/').status_code, 404)
