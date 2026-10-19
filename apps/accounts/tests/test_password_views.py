import re
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts import views
from apps.accounts.factories import UserFactory
from apps.accounts.tests.test_auth_methods import ENTRA_UNCONFIGURED, messages_of, set_methods
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.accounts.throttles import LoginEmailThrottle
from apps.accounts.tokens import make_link
from apps.core.keys import uuid7

GOOD_PASSWORD = 'correct-horse-battery'
NEW_PASSWORD = 'staple-garden-lamp'
FAILING_BACKEND = 'apps.accounts.tests.test_password_views.FailingEmailBackend'
AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class FailingEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        raise OSError('mail server unreachable')


def user_with_password(password=GOOD_PASSWORD, **kwargs):
    user = UserFactory(**kwargs)
    user.set_password(password)
    user.save()
    return user


def input_tag(html, name):
    return re.search(rf'<input[^>]*name="{name}"[^>]*>', html).group(0)


def link_path(user):
    return urlsplit(make_link(RequestFactory().get('/'), user)).path


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class SignInPageTest(TestCase):

    def assert_page(self, entra, password):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')
        self.assertEqual('id="loginBtn"' in response.content.decode(), entra)
        self.assertEqual('id="passwordLoginForm"' in response.content.decode(), password)
        self.assertEqual('Forgot password?' in response.content.decode(), password)
        self.assertEqual('id="loginDivider"' in response.content.decode(), entra and password)
        self.assertEqual('No sign-in method is enabled.' in response.content.decode(), not entra and not password)
        return response

    def test_microsoft_only_by_default(self):
        self.assert_page(entra=True, password=False)

    def test_both(self):
        set_methods(True, True)
        self.assert_page(entra=True, password=True)

    def test_password_only(self):
        set_methods(False, True)
        self.assert_page(entra=False, password=True)

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_neither_when_entra_is_not_configured(self):
        set_methods(True, False)
        response = self.assert_page(entra=False, password=False)
        self.assertContains(response, 'Contact a system administrator.')

    def test_next_is_carried_into_the_form(self):
        set_methods(True, True)
        response = self.client.get('/?next=/profile/')
        self.assertContains(response, 'name="next" value="/profile/"')


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class PasswordSignInTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)
        self.user = user_with_password(email='signin@example.com')

    def sign_in(self, email, password, **extra):
        return self.client.post('/', {'email': email, 'password': password, **extra})

    def signed_in(self):
        return '_auth_user_id' in self.client.session

    def test_redirects_with_the_message_when_off(self):
        set_methods(True, False)
        response = self.sign_in(self.user.email, GOOD_PASSWORD)
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), ['Password sign-in is turned off.'])
        self.assertFalse(self.signed_in())

    def test_correct_credentials_sign_in_and_land_on_the_dashboard(self):
        response = self.sign_in(self.user.email, GOOD_PASSWORD)
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))

    def test_the_address_is_matched_case_insensitively(self):
        self.sign_in('SignIn@Example.COM', GOOD_PASSWORD)
        self.assertTrue(self.signed_in())

    def test_a_safe_next_is_followed(self):
        response = self.sign_in(self.user.email, GOOD_PASSWORD, next='/profile/')
        self.assertRedirects(response, '/profile/', fetch_redirect_response=False)

    def test_an_external_next_is_ignored(self):
        for target in ('https://evil.example/', '//evil.example/x', 'http://testserver.evil.example/'):
            with self.subTest(target=target):
                self.client.logout()
                response = self.sign_in(self.user.email, GOOD_PASSWORD, next=target)
                self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)

    def test_wrong_address_wrong_password_and_no_password_give_one_message(self):
        no_password = UserFactory(email='nopass@example.com')
        no_password.set_unusable_password()
        no_password.save()
        attempts = (
            ('unknown@example.com', GOOD_PASSWORD),
            (self.user.email, 'wrong-password-xyz'),
            (no_password.email, GOOD_PASSWORD),
            ('', GOOD_PASSWORD),
            ('not-an-address', GOOD_PASSWORD),
        )
        for email, password in attempts:
            with self.subTest(email=email):
                response = self.sign_in(email, password)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'accounts/login.html')
                self.assertEqual(messages_of(response), ['Incorrect email address or password.'])
                self.assertFalse(self.signed_in())

    def test_a_duplicate_address_is_refused_with_the_same_message(self):
        user_with_password(email='Dupe@example.com')
        user_with_password(email='dupe@example.com')
        response = self.sign_in('dupe@example.com', GOOD_PASSWORD)
        self.assertEqual(messages_of(response), ['Incorrect email address or password.'])
        self.assertFalse(self.signed_in())

    def test_inactive_with_the_correct_password_gives_the_deactivation_message(self):
        inactive = user_with_password(email='inactive@example.com', is_active=False)
        response = self.sign_in(inactive.email, GOOD_PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(messages_of(response), ['Your account has been deactivated. Contact a system administrator.'])
        self.assertFalse(self.signed_in())

    def test_inactive_with_a_wrong_password_gives_the_generic_message(self):
        inactive = user_with_password(email='inactive@example.com', is_active=False)
        response = self.sign_in(inactive.email, 'wrong-password-xyz')
        self.assertEqual(messages_of(response), ['Incorrect email address or password.'])

    def test_the_sixth_attempt_within_five_minutes_for_one_address_is_throttled(self):
        for _ in range(5):
            self.assertEqual(messages_of(self.sign_in(self.user.email, 'wrong-password-xyz')), ['Incorrect email address or password.'])
        response = self.sign_in(self.user.email, GOOD_PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(messages_of(response), ['Too many attempts. Try again in a few minutes.'])
        self.assertFalse(self.signed_in())
        other = user_with_password(email='other@example.com')
        self.sign_in(other.email, GOOD_PASSWORD)
        self.assertTrue(self.signed_in())

    def test_successful_attempts_count_towards_the_limit(self):
        for _ in range(5):
            self.sign_in(self.user.email, GOOD_PASSWORD)
            self.assertTrue(self.signed_in())
            self.client.logout()
        response = self.sign_in(self.user.email, GOOD_PASSWORD)
        self.assertEqual(messages_of(response), ['Too many attempts. Try again in a few minutes.'])
        self.assertFalse(self.signed_in())

    def test_the_email_limit_is_five_per_five_minutes(self):
        throttle = LoginEmailThrottle()
        self.assertEqual((throttle.num_requests, throttle.duration), (5, 300))

    def test_failures_are_logged_with_address_and_client_but_never_the_password(self):
        with self.assertLogs('apps.accounts.views', level='INFO') as logs:
            self.sign_in(self.user.email, 'wrong-password-xyz')
            self.sign_in('unknown@example.com', 'wrong-password-xyz')
            inactive = user_with_password(email='inactive@example.com', is_active=False)
            self.sign_in(inactive.email, GOOD_PASSWORD)
        self.assertEqual(len(logs.output), 3)
        for record, email in zip(logs.output, (self.user.email, 'unknown@example.com', inactive.email)):
            self.assertIn(email, record)
            self.assertIn('127.0.0.1', record)
        joined = '\n'.join(logs.output)
        self.assertNotIn('wrong-password-xyz', joined)
        self.assertNotIn(GOOD_PASSWORD, joined)

    def test_a_missing_account_and_a_wrong_password_both_run_one_hash(self):
        no_password = UserFactory(email='nopass@example.com')
        no_password.set_unusable_password()
        no_password.save()
        views.dummy_hash()
        with patch('django.contrib.auth.hashers.PBKDF2PasswordHasher.verify', return_value=False) as verify:
            for email in ('unknown@example.com', self.user.email, no_password.email):
                with self.subTest(email=email):
                    verify.reset_mock()
                    self.sign_in(email, 'wrong-password-xyz')
                    self.assertEqual(verify.call_count, 1)

    def test_a_signed_in_user_posting_is_sent_to_the_dashboard(self):
        self.client.force_login(self.user)
        response = self.sign_in(self.user.email, GOOD_PASSWORD)
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)

    def test_no_page_response_contains_the_password(self):
        for email, password in ((self.user.email, 'wrong-password-xyz'), ('unknown@example.com', 'wrong-password-xyz')):
            response = self.sign_in(email, password)
            self.assertNotContains(response, password)


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class ForgotPasswordTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)
        self.user = UserFactory(email='forgot@example.com')

    def forgot(self, email):
        return self.client.post('/password/forgot/', {'email': email})

    def test_redirects_with_the_message_when_off(self):
        set_methods(True, False)
        responses = (Client().get('/password/forgot/'), Client().post('/password/forgot/', {'email': self.user.email}))
        for response in responses:
            self.assertRedirects(response, '/', fetch_redirect_response=False)
            self.assertEqual(messages_of(response), ['Password sign-in is turned off.'])
        self.assertEqual(mail.outbox, [])

    def test_get_renders_the_form(self):
        response = self.client.get('/password/forgot/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/forgot_password.html')
        self.assertContains(response, 'name="email"')

    def test_a_known_active_address_gets_one_email_and_the_sent_page(self):
        response = self.forgot(self.user.email)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/forgot_sent.html')
        self.assertContains(response, f'If an account exists for <strong>{self.user.email}</strong>, a link to set a new password has been sent to it.')
        self.assertContains(response, 'The link works once and expires in 1 day.')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.subject, 'ArcSpec - Set your password')
        self.assertIn('http://testserver/password/set/', message.body)
        self.assertIn('http://testserver/password/set/', message.alternatives[0].content)

    def test_unknown_and_inactive_addresses_get_no_email_and_the_same_page(self):
        UserFactory(email='inactive@example.com', is_active=False)
        pages = set()
        for email in ('unknown@example.com', 'inactive@example.com', 'FORGOT@example.com'):
            with self.subTest(email=email):
                response = self.forgot(email)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'accounts/forgot_sent.html')
                self.assertContains(response, f'<strong>{email}</strong>')
                pages.add(response.content.decode().replace(email, 'ADDRESS'))
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_an_invalid_address_re_renders_the_form(self):
        response = self.forgot('not-an-address')
        self.assertTemplateUsed(response, 'accounts/forgot_password.html')
        self.assertEqual(mail.outbox, [])

    def test_the_sixth_request_within_a_minute_for_one_address_is_throttled(self):
        for _ in range(5):
            self.assertTemplateUsed(self.forgot(self.user.email), 'accounts/forgot_sent.html')
        response = self.forgot(self.user.email)
        self.assertTemplateUsed(response, 'accounts/forgot_password.html')
        self.assertEqual(messages_of(response), ['Too many attempts. Try again in a few minutes.'])
        self.assertEqual(len(mail.outbox), 5)

    @override_settings(EMAIL_BACKEND=FAILING_BACKEND)
    def test_a_mail_failure_is_logged_and_reported(self):
        with self.assertLogs('apps.accounts.views', level='ERROR') as logs:
            response = self.forgot(self.user.email)
        self.assertTemplateUsed(response, 'accounts/forgot_password.html')
        self.assertEqual(messages_of(response), ['The email could not be sent. Try again later.'])
        self.assertIn('mail server unreachable', logs.output[0])

    def test_the_emailed_link_opens_the_set_password_page(self):
        self.forgot(self.user.email)
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith('http://testserver/'))
        response = self.client.get(urlsplit(link).path)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/set_password.html')


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class SetPasswordTest(TestCase):

    def setUp(self):
        set_methods(True, True)
        self.user = UserFactory(email='invitee@example.com')
        self.user.set_unusable_password()
        self.user.save()
        self.path = link_path(self.user)

    def set_password(self, path, password1, password2=None):
        return self.client.post(path, {'new_password1': password1, 'new_password2': password2 or password1})

    def test_redirects_with_the_message_when_off(self):
        set_methods(True, False)
        responses = (
            Client().get(self.path),
            Client().post(self.path, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}),
        )
        for response in responses:
            self.assertRedirects(response, '/', fetch_redirect_response=False)
            self.assertEqual(messages_of(response), ['Password sign-in is turned off.'])
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_a_valid_link_renders_the_form(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/set_password.html')
        self.assertContains(response, self.user.email)
        self.assertContains(response, 'name="new_password1"')

    def test_a_wrong_token_an_unknown_key_and_an_inactive_user_render_the_invalid_page(self):
        inactive = UserFactory(email='inactive@example.com', is_active=False)
        wrong_token = self.path.rsplit('/', 2)[0] + '/abcdef-0123456789abcdef0123456789abcdef/'
        for path in (wrong_token, f'/password/set/{uuid7()}/abc-def/', link_path(inactive)):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'accounts/set_password_invalid.html')
                self.assertContains(response, '/password/forgot/')

    def test_a_key_that_is_not_a_uuid_is_404(self):
        for path in ('/password/set/1/abc-def/', '/password/set/not-a-key/abc-def/', f'/password/set/{self.user.pk}/abc-def/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_an_expired_link_renders_the_invalid_page(self):
        later = datetime.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 60)
        with patch.object(PasswordResetTokenGenerator, '_now', return_value=later):
            response = self.client.get(self.path)
        self.assertTemplateUsed(response, 'accounts/set_password_invalid.html')

    def test_a_weak_password_is_refused(self):
        for password in ('short', 'password1234', '123456789012', self.user.email):
            with self.subTest(password=password):
                response = self.set_password(self.path, password)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'accounts/set_password.html')
                self.assertTrue(response.context['form'].errors)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_a_mismatch_is_refused(self):
        response = self.set_password(self.path, NEW_PASSWORD, NEW_PASSWORD + 'x')
        self.assertTrue(response.context['form'].errors)

    def test_eleven_characters_are_refused_and_twelve_accepted(self):
        response = self.set_password(self.path, 'vb7-qx2-nn4')
        self.assertIn('new_password2', response.context['form'].errors)
        response = self.set_password(self.path, 'vb7-qx2-nn4p')
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('vb7-qx2-nn4p'))

    def test_a_valid_password_is_stored_signs_in_and_kills_the_link(self):
        response = self.set_password(self.path, NEW_PASSWORD)
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), ['Password set. You can sign in now.'])
        self.assertNotIn('_auth_user_id', self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertTemplateUsed(self.client.get(self.path), 'accounts/set_password_invalid.html')
        self.assertTemplateUsed(self.set_password(self.path, 'another-good-one'), 'accounts/set_password_invalid.html')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.client.post('/', {'email': self.user.email, 'password': NEW_PASSWORD})
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))

    def test_a_link_dies_when_the_user_signs_in_first(self):
        self.client.force_login(self.user)
        self.user.refresh_from_db()
        self.client.logout()
        self.assertTemplateUsed(self.client.get(self.path), 'accounts/set_password_invalid.html')

    def test_no_page_response_contains_the_password(self):
        for response in (self.set_password(self.path, 'zq9-tiny'), self.set_password(self.path, NEW_PASSWORD + 'x', NEW_PASSWORD)):
            self.assertNotContains(response, NEW_PASSWORD)
            self.assertNotContains(response, 'zq9-tiny')


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class ChangePasswordTest(TestCase):

    def setUp(self):
        set_methods(True, True)
        self.user = user_with_password(email='changer@example.com')
        self.client.force_login(self.user)

    def change(self, old, new, confirm=None, origin='profile', **headers):
        return self.client.post('/password/change/', {
            'old_password': old, 'new_password1': new, 'new_password2': confirm or new, 'origin': origin,
        }, **headers)

    def dialog(self):
        return self.client.get(reverse('modal', args=['change_password']), **AJAX)

    def test_anonymous_is_sent_to_sign_in(self):
        self.client.logout()
        self.assertRedirects(self.change(GOOD_PASSWORD, NEW_PASSWORD), '/?next=/password/change/', fetch_redirect_response=False)

    def test_the_dialog_is_refused_and_the_post_redirects_with_the_message_when_off(self):
        set_methods(True, False)
        self.assertEqual(self.dialog().status_code, 403)
        response = self.change(GOOD_PASSWORD, NEW_PASSWORD)
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), ['Password sign-in is turned off.'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(GOOD_PASSWORD))

    def test_a_user_without_a_password_is_refused(self):
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.dialog().status_code, 403)
        self.assertEqual(self.change('', NEW_PASSWORD).status_code, 403)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_a_refused_change_returns_the_dialog_with_focus_on_the_first_error(self):
        for old, new, confirm, field in (
            ('not-the-current-one', NEW_PASSWORD, NEW_PASSWORD, 'old_password'),
            (GOOD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD + 'x', 'new_password2'),
        ):
            with self.subTest(field=field):
                response = self.change(old, new, confirm, **AJAX)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(list(response.context['form'].errors), [field])
                self.assertEqual(response.context['focus'], field)
                self.assertIn('autofocus', input_tag(response.content.decode(), field))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(GOOD_PASSWORD))

    def test_a_refused_change_without_the_dialog_returns_with_the_error(self):
        response = self.change('not-the-current-one', NEW_PASSWORD, origin='settings')
        self.assertRedirects(response, '/settings/#account', fetch_redirect_response=False)
        self.assertEqual(len(messages_of(response)), 1)

    def test_the_change_returns_to_the_page_the_dialog_was_opened_from(self):
        for origin, target in (('profile', '/profile/'), ('settings', '/settings/#account'), ('https://example.com/', '/profile/')):
            with self.subTest(origin=origin):
                self.user.set_password(GOOD_PASSWORD)
                self.user.save()
                self.client = Client()
                self.client.force_login(self.user)
                response = self.change(GOOD_PASSWORD, NEW_PASSWORD, origin=origin)
                self.assertRedirects(response, target, fetch_redirect_response=False)
                self.assertEqual(messages_of(response), ['Password changed.'])
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_the_dialog_posts_back_its_origin(self):
        for origin, expected in (('settings', 'settings'), ('elsewhere', 'profile')):
            with self.subTest(origin=origin):
                response = self.client.get(reverse('modal', args=['change_password']), {'origin': origin}, **AJAX)
                self.assertEqual(response.context['origin'], expected)

    def test_eleven_characters_are_refused_and_twelve_accepted(self):
        response = self.change(GOOD_PASSWORD, 'vb7-qx2-nn4', **AJAX)
        self.assertIn('new_password2', response.context['form'].errors)
        response = self.change(GOOD_PASSWORD, 'vb7-qx2-nn4p')
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('vb7-qx2-nn4p'))

    def test_profile_and_settings_offer_the_dialog_only_while_password_sign_in_is_on(self):
        for path, origin in (('/profile/', 'profile'), ('/settings/', 'settings')):
            with self.subTest(path=path):
                set_methods(True, True)
                self.assertContains(self.client.get(path), f'data-modal-open="change_password" data-origin="{origin}"')
                set_methods(True, False)
                self.assertNotContains(self.client.get(path), 'data-modal-open="change_password"')

    def test_no_response_contains_the_password(self):
        response = self.change('not-the-current-one', NEW_PASSWORD, **AJAX)
        self.assertNotContains(response, NEW_PASSWORD, status_code=422)
        self.assertNotContains(response, 'not-the-current-one', status_code=422)
