import os
import runpy
from importlib import reload
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import environ
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import clear_url_caches, resolve, reverse

import config.urls

ENTRA_CONFIGURED = {
    'microsoft': {
        'APPS': [{
            'client_id': 'test-client-id',
            'secret': 'test-client-secret',
            'settings': {'tenant': 'test-tenant'},
        }],
        'SCOPE': ['openid', 'email', 'profile', 'User.Read'],
        'AUTH_PARAMS': {'prompt': 'select_account'},
    }
}


def rebuild_urlconf():
    reload(config.urls)
    clear_url_caches()


def redirect_uri_of(response):
    location = urlsplit(response['Location'])
    return location.netloc, parse_qs(location.query)['redirect_uri']


class MicrosoftStartUrlTest(TestCase):

    def test_routes_use_the_configured_segment(self):
        prefix = settings.AUTH_CALLBACK_PREFIX
        self.assertEqual(reverse('microsoft_login'), '/auth/microsoft/')
        self.assertEqual(reverse('microsoft_callback'), f'/auth/callback/{prefix}/microsoft/login/callback/')

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
    def test_start_url_redirects_to_microsoft_with_the_configured_callback(self):
        response = self.client.get(reverse('microsoft_login'))
        self.assertEqual(response.status_code, 302)
        host, redirect_uri = redirect_uri_of(response)
        self.assertEqual(host, 'login.microsoftonline.com')
        self.assertEqual(
            redirect_uri,
            [f'http://testserver/auth/callback/{settings.AUTH_CALLBACK_PREFIX}/microsoft/login/callback/'],
        )


class CallbackPrefixOverrideTest(TestCase):

    def setUp(self):
        self.addCleanup(rebuild_urlconf)

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
    def test_the_callback_follows_the_setting_and_the_start_does_not(self):
        old = settings.AUTH_CALLBACK_PREFIX
        with override_settings(AUTH_CALLBACK_PREFIX='other-segment'):
            rebuild_urlconf()
            self.assertEqual(resolve('/auth/microsoft/').url_name, 'microsoft_login')
            self.assertEqual(
                resolve('/auth/callback/other-segment/microsoft/login/callback/').url_name, 'microsoft_callback'
            )
            self.assertEqual(self.client.get('/auth/callback/other-segment/microsoft/login/').status_code, 404)
            self.assertEqual(self.client.get(f'/auth/callback/{old}/microsoft/login/callback/').status_code, 404)
            response = self.client.get('/auth/microsoft/')
            self.assertEqual(response.status_code, 302)
            host, redirect_uri = redirect_uri_of(response)
            self.assertEqual(host, 'login.microsoftonline.com')
            self.assertEqual(redirect_uri, ['http://testserver/auth/callback/other-segment/microsoft/login/callback/'])


class MissingKeyTest(SimpleTestCase):

    def test_settings_refuse_to_load_without_the_key(self):
        base_settings = settings.BASE_DIR / 'config' / 'settings' / 'base.py'
        with patch.dict(os.environ), patch.object(environ.Env, 'read_env'):
            os.environ.pop('AUTH_CALLBACK_PREFIX', None)
            with self.assertRaises(ImproperlyConfigured) as raised:
                runpy.run_path(str(base_settings))
        self.assertIn('AUTH_CALLBACK_PREFIX', str(raised.exception))
