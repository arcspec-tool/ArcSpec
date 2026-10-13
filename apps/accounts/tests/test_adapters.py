from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.adapters import AccountAdapter, InviteOnlySocialAccountAdapter
from apps.accounts.factories import UserFactory
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED

CANCELLED = 'Microsoft sign-in was cancelled.'
FAILED = 'Microsoft sign-in failed. Try again or contact a system administrator.'
DEACTIVATED = 'Your account has been deactivated. Contact a system administrator.'


def request_with_messages():
    request = RequestFactory().get('/')
    request.session = {}
    setattr(request, '_messages', FallbackStorage(request))
    return request


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class InviteOnlySocialAccountAdapterTest(TestCase):

    def setUp(self):
        self.adapter = InviteOnlySocialAccountAdapter()
        self.factory = RequestFactory()

    def test_is_not_open_for_signup(self):
        request = self.factory.get('/')
        result = self.adapter.is_open_for_signup(request, MagicMock())
        self.assertFalse(result)

    def test_pre_social_login_no_email_raises(self):
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {}

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(request, sociallogin)

    def test_pre_social_login_unknown_email_raises(self):
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {'mail': 'unknown@example.com'}

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(request, sociallogin)

    def test_pre_social_login_inactive_user_raises(self):
        UserFactory(email='inactive@example.com', is_active=False)
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {'mail': 'inactive@example.com'}

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(request, sociallogin)

    def test_pre_social_login_active_user_succeeds(self):
        UserFactory(email='active@example.com', is_active=True)
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {
            'mail': 'active@example.com',
            'displayName': 'Test User',
        }
        sociallogin.is_existing = True

        self.adapter.pre_social_login(request, sociallogin)

    def test_pre_social_login_populates_display_name(self):
        user = UserFactory(email='dn@example.com', display_name='')
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {
            'mail': 'dn@example.com',
            'displayName': 'Full Name',
        }
        sociallogin.is_existing = True

        self.adapter.pre_social_login(request, sociallogin)
        user.refresh_from_db()
        self.assertEqual(user.display_name, 'Full Name')

    def test_pre_social_login_multiple_users_same_email_raises(self):
        UserFactory(email='dupe@example.com')
        UserFactory(email='Dupe@example.com')
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {'mail': 'dupe@example.com'}

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(request, sociallogin)

    def test_pre_social_login_connects_new_social_account(self):
        user = UserFactory(email='connect@example.com')
        request = request_with_messages()

        sociallogin = MagicMock()
        sociallogin.account.extra_data = {'mail': 'connect@example.com'}
        sociallogin.is_existing = False

        self.adapter.pre_social_login(request, sociallogin)
        sociallogin.connect.assert_called_once_with(request, user)


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class NameUpdateTest(TestCase):

    def setUp(self):
        self.adapter = InviteOnlySocialAccountAdapter()

    def sign_in(self, user, **extra):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {'mail': user.email, **extra}
        sociallogin.is_existing = True
        self.adapter.pre_social_login(request_with_messages(), sociallogin)
        user.refresh_from_db()
        return user

    def test_names_are_filled_at_the_first_sign_in_and_updated_at_the_next(self):
        user = UserFactory(first_name='', last_name='', display_name='')
        self.sign_in(user, givenName='Given', surname='Sur', displayName='Given Sur')
        self.assertEqual((user.first_name, user.last_name, user.display_name), ('Given', 'Sur', 'Given Sur'))
        self.sign_in(user, givenName='Renamed', surname='Sur', displayName='Renamed Sur')
        self.assertEqual((user.first_name, user.last_name, user.display_name), ('Renamed', 'Sur', 'Given Sur'))

    def test_names_typed_on_the_profile_are_replaced_by_microsoft_names(self):
        user = UserFactory(first_name='Typed', last_name='ByHand')
        self.sign_in(user, givenName='Given', surname='Sur')
        self.assertEqual((user.first_name, user.last_name), ('Given', 'Sur'))

    def test_missing_or_empty_microsoft_names_change_nothing(self):
        user = UserFactory(first_name='Kept', last_name='Kept', display_name='Kept Kept')
        self.sign_in(user, givenName='', displayName=None)
        self.assertEqual((user.first_name, user.last_name, user.display_name), ('Kept', 'Kept', 'Kept Kept'))


class AccountAdapterTest(TestCase):

    def test_inactive_user_ends_at_login_with_the_message(self):
        request = request_with_messages()
        response = AccountAdapter().respond_user_inactive(request, UserFactory(is_active=False))
        self.assertEqual((response.status_code, response['Location']), (302, '/'))
        self.assertEqual([str(m) for m in get_messages(request)], [DEACTIVATED])


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class AuthenticationErrorTest(TestCase):

    def assert_ends_at_login_with(self, response, message):
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(response.templates, [])
        self.assertContains(self.client.get('/'), message)

    def test_cancelled_sign_in_ends_at_login_with_the_message(self):
        start = self.client.get(reverse('microsoft_login'))
        state = parse_qs(urlsplit(start['Location']).query)['state'][0]
        response = self.client.get(reverse('microsoft_callback'), {'error': 'access_denied', 'state': state})
        self.assert_ends_at_login_with(response, CANCELLED)

    def test_unknown_state_ends_at_login_with_the_failure_message(self):
        with self.assertLogs('apps.accounts.adapters', level='ERROR') as logs:
            response = self.client.get(reverse('microsoft_callback'), {'code': 'x', 'state': 'unknown'})
        self.assert_ends_at_login_with(response, FAILED)
        self.assertIn('Microsoft sign-in failed: unknown', logs.output[0])
