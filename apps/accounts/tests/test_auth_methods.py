from io import StringIO
from unittest.mock import MagicMock

from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts import auth_methods
from apps.accounts.adapters import InviteOnlySocialAccountAdapter
from apps.accounts.factories import UserFactory
from apps.accounts.tests.test_adapters import request_with_messages
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED, redirect_uri_of
from apps.administration.models import SystemSettings

ENTRA_UNCONFIGURED = {
    'microsoft': {
        'APPS': [{
            'client_id': '',
            'secret': '',
            'settings': {'tenant': ''},
        }],
        'SCOPE': ['openid', 'email', 'profile', 'User.Read'],
        'AUTH_PARAMS': {'prompt': 'select_account'},
    }
}

ENTRA_OFF = 'Microsoft sign-in is turned off.'


def set_methods(entra=True, password=False):
    stored = SystemSettings.load()
    stored.entra_login_enabled = entra
    stored.password_login_enabled = password
    stored.save()
    return stored


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def with_one_key_empty(key):
    app = {'client_id': 'id', 'secret': 'secret', 'settings': {'tenant': 'tenant'}}
    if key == 'tenant':
        app['settings']['tenant'] = ''
    else:
        app[key] = ''
    return {'microsoft': {'APPS': [app]}}


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class CurrentStateTest(TestCase):

    def test_the_default_state_is_microsoft_only(self):
        self.assertEqual(auth_methods.current(), (True, False))

    def test_each_row_of_the_behaviour_table(self):
        for entra, password in ((True, False), (True, True), (False, True)):
            with self.subTest(entra=entra, password=password):
                set_methods(entra, password)
                self.assertEqual(auth_methods.current(), (entra, password))
        set_methods(True, False)
        with self.subTest(entra=False, password=False), override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED):
            self.assertEqual(auth_methods.current(), (False, False))

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_entra_stored_on_but_not_configured_is_off(self):
        set_methods(True, True)
        self.assertFalse(auth_methods.entra_configured())
        self.assertEqual(auth_methods.current(), (False, True))

    def test_a_given_row_is_read_without_a_query(self):
        stored = SystemSettings(entra_login_enabled=False, password_login_enabled=True)
        with self.assertNumQueries(0):
            self.assertEqual(auth_methods.current(stored), (False, True))


class EntraConfiguredTest(TestCase):

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
    def test_all_three_values_present(self):
        self.assertTrue(auth_methods.entra_configured())

    def test_any_empty_value_means_not_configured(self):
        for key in ('client_id', 'secret', 'tenant'):
            with self.subTest(key=key), override_settings(SOCIALACCOUNT_PROVIDERS=with_one_key_empty(key)):
                self.assertFalse(auth_methods.entra_configured())


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class ValidateTest(TestCase):

    def test_every_allowed_combination(self):
        for entra, password in ((True, False), (True, True), (False, True)):
            with self.subTest(entra=entra, password=password):
                self.assertEqual(auth_methods.validate(entra, password), [])

    def test_both_off_is_refused(self):
        self.assertEqual(auth_methods.validate(False, False), ['At least one sign-in method must stay on.'])

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_entra_on_while_not_configured_is_refused(self):
        self.assertEqual(auth_methods.validate(True, True), ['Microsoft sign-in cannot be turned on: it is not configured in this environment.'])
        self.assertEqual(auth_methods.validate(True, False), ['Microsoft sign-in cannot be turned on: it is not configured in this environment.'])
        self.assertEqual(auth_methods.validate(False, False), ['At least one sign-in method must stay on.'])
        self.assertEqual(auth_methods.validate(False, True), [])


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class EntraLoginGateTest(TestCase):

    def test_redirects_with_the_message_when_off(self):
        set_methods(False, True)
        response = self.client.get(reverse('microsoft_login'))
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), [ENTRA_OFF])

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_redirects_with_the_message_when_not_configured(self):
        response = self.client.get(reverse('microsoft_login'))
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), [ENTRA_OFF])

    def test_redirects_to_microsoft_with_the_configured_callback_when_on(self):
        response = self.client.get(reverse('microsoft_login'))
        self.assertEqual(response.status_code, 302)
        host, redirect_uri = redirect_uri_of(response)
        self.assertEqual(host, 'login.microsoftonline.com')
        self.assertIn(settings.AUTH_CALLBACK_PREFIX, redirect_uri[0])


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class PreSocialLoginGateTest(TestCase):

    @staticmethod
    def sociallogin(email):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {'mail': email}
        sociallogin.is_existing = False
        return sociallogin

    def test_refuses_when_entra_is_off_before_looking_at_the_email(self):
        user = UserFactory(email='gate@example.com')
        set_methods(False, True)
        request = request_with_messages()
        sociallogin = self.sociallogin(user.email)
        with self.assertRaises(ImmediateHttpResponse) as raised:
            InviteOnlySocialAccountAdapter().pre_social_login(request, sociallogin)
        self.assertEqual(raised.exception.response['Location'], '/')
        self.assertEqual([str(m) for m in get_messages(request)], [ENTRA_OFF])
        sociallogin.connect.assert_not_called()

    def test_connects_as_before_when_on(self):
        user = UserFactory(email='gate-on@example.com')
        request = request_with_messages()
        sociallogin = self.sociallogin(user.email)
        InviteOnlySocialAccountAdapter().pre_social_login(request, sociallogin)
        sociallogin.connect.assert_called_once_with(request, user)


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class CommandTest(TestCase):

    @staticmethod
    def run_command(*args):
        out = StringIO()
        call_command('auth_methods', *args, stdout=out)
        return out.getvalue()

    def test_prints_the_state(self):
        self.assertEqual(self.run_command(), 'entra: on\npassword: off\nentra configured: yes\n')

    def test_password_round_trips(self):
        self.assertEqual(self.run_command('--password', 'on'), 'entra: on\npassword: on\nentra configured: yes\n')
        self.assertTrue(SystemSettings.load().password_login_enabled)
        self.assertEqual(self.run_command('--password', 'off'), 'entra: on\npassword: off\nentra configured: yes\n')
        self.assertFalse(SystemSettings.load().password_login_enabled)

    def test_both_off_exits_1_and_changes_nothing(self):
        with self.assertRaises(CommandError) as raised:
            call_command('auth_methods', '--entra', 'off', '--password', 'off')
        self.assertEqual((str(raised.exception), raised.exception.returncode), ('At least one sign-in method must stay on.', 1))
        self.assertEqual(auth_methods.current(), (True, False))

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_entra_on_while_not_configured_exits_1(self):
        with self.assertRaises(CommandError) as raised:
            call_command('auth_methods', '--password', 'on')
        self.assertEqual(str(raised.exception), 'Microsoft sign-in cannot be turned on: it is not configured in this environment.')
        self.assertEqual(
            self.run_command('--entra', 'off', '--password', 'on'),
            'entra: off\npassword: on\nentra configured: no\n',
        )
        self.assertEqual(auth_methods.current(), (False, True))
