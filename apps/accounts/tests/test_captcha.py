import io
import json
from unittest.mock import patch
from urllib.parse import parse_qs

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.accounts.factories import UserFactory
from apps.accounts.tests.test_auth_methods import messages_of, set_methods
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.accounts.tests.test_password_views import GOOD_PASSWORD, user_with_password
from apps.administration.models import SystemSettings

KEYS = {
    'turnstile': {'site_key': 'turnstile-site', 'secret_key': 'turnstile-secret'},
    'hcaptcha': {'site_key': 'hcaptcha-site', 'secret_key': 'hcaptcha-secret'},
}
TOKEN_FIELDS = {'turnstile': 'cf-turnstile-response', 'hcaptcha': 'h-captcha-response'}
VERIFY_REQUESTS = {
    'turnstile': ('https://challenges.cloudflare.com/turnstile/v0/siteverify', {'secret': ['turnstile-secret'], 'response': ['token']}),
    'hcaptcha': ('https://api.hcaptcha.com/siteverify', {'secret': ['hcaptcha-secret'], 'response': ['token'], 'sitekey': ['hcaptcha-site']}),
}
URLOPEN = 'apps.accounts.captcha.urlopen'


def answer(success):
    return lambda request, timeout: io.BytesIO(json.dumps({'success': success}).encode())


def set_captcha(name):
    stored = SystemSettings.load()
    stored.captcha_provider = name
    stored.save()


def frame_sources(response):
    directives = dict(part.strip().partition(' ')[::2] for part in response['Content-Security-Policy'].split(';'))
    return directives.get('frame-src')


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED, CAPTCHA_KEYS=KEYS)
class CaptchaSignInTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)
        self.user = user_with_password(email='captcha@example.com')

    def sign_in(self, provider, token):
        return self.client.post('/', {'email': self.user.email, 'password': GOOD_PASSWORD, TOKEN_FIELDS[provider]: token})

    def signed_in(self):
        return '_auth_user_id' in self.client.session

    def test_a_token_confirmed_by_one_provider_request_signs_in(self):
        for provider, (url, data) in VERIFY_REQUESTS.items():
            with self.subTest(provider=provider), patch(URLOPEN, side_effect=answer(True)) as urlopen:
                set_captcha(provider)
                response = self.sign_in(provider, 'token')
                self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
                self.assertEqual(urlopen.call_count, 1)
                request = urlopen.call_args.args[0]
                self.assertEqual((request.full_url, parse_qs(request.data.decode())), (url, data))
                self.client.logout()

    def test_sign_in_is_refused_unless_the_provider_confirms_the_token(self):
        cases = (
            ('', 'Complete the verification and try again.', 0),
            ('token', 'The verification failed. Try again.', 1),
        )
        for provider in KEYS:
            set_captcha(provider)
            for token, message, calls in cases:
                with self.subTest(provider=provider, token=token), patch(URLOPEN, side_effect=answer(False)) as urlopen:
                    response = self.sign_in(provider, token)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(messages_of(response), [message])
                    self.assertEqual(urlopen.call_count, calls)
                    self.assertFalse(self.signed_in())

    def test_an_unreachable_or_unreadable_provider_refuses_and_logs_the_failure(self):
        set_captcha('turnstile')
        effects = (TimeoutError('timed out'), lambda request, timeout: io.BytesIO(b'<html>'))
        for effect in effects:
            with self.subTest(effect=effect):
                with patch(URLOPEN, side_effect=effect), self.assertLogs('apps.accounts.captcha', level='ERROR') as logs:
                    response = self.sign_in('turnstile', 'token')
                self.assertEqual(messages_of(response), ['The verification service could not be reached. Try again later.'])
                self.assertFalse(self.signed_in())
                self.assertEqual(len(logs.output), 1)

    def test_refused_tokens_do_not_count_towards_the_email_limit(self):
        set_captcha('turnstile')
        token = {TOKEN_FIELDS['turnstile']: 'token'}
        for path, data in (('/', {'email': self.user.email, 'password': GOOD_PASSWORD}), ('/password/forgot/', {'email': self.user.email})):
            cache.clear()
            mail.outbox = []
            client = Client()
            with self.subTest(path=path):
                with patch(URLOPEN, side_effect=answer(False)):
                    for _ in range(6):
                        client.post(path, {**data, **token})
                with patch(URLOPEN, side_effect=answer(True)):
                    response = client.post(path, {**data, **token})
                if path == '/':
                    self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
                else:
                    self.assertTemplateUsed(response, 'accounts/forgot_sent.html')
                    self.assertEqual(len(mail.outbox), 1)

    def test_a_request_over_the_address_limit_sends_no_verification_request(self):
        set_captcha('turnstile')
        token = {TOKEN_FIELDS['turnstile']: 'token'}
        cases = (
            ('/', {'email': self.user.email, 'password': GOOD_PASSWORD}, 30, 'accounts/login.html'),
            ('/password/forgot/', {'email': self.user.email}, 20, 'accounts/forgot_password.html'),
        )
        for path, data, limit, template in cases:
            cache.clear()
            client = Client()
            with self.subTest(path=path):
                with patch(URLOPEN, side_effect=answer(False)):
                    for _ in range(limit):
                        client.post(path, {**data, **token})
                with patch(URLOPEN, side_effect=answer(True)) as urlopen:
                    response = client.post(path, {**data, **token})
                self.assertTemplateUsed(response, template)
                self.assertEqual(messages_of(response), ['Too many attempts. Try again in a few minutes.'])
                self.assertEqual(urlopen.call_count, 0)

    def test_no_verification_while_the_captcha_is_off_or_has_no_keys(self):
        cases = (('', KEYS), ('turnstile', {**KEYS, 'turnstile': {'site_key': 'turnstile-site', 'secret_key': ''}}))
        for provider, keys in cases:
            with self.subTest(provider=provider), override_settings(CAPTCHA_KEYS=keys), patch(URLOPEN) as urlopen:
                set_captcha(provider)
                response = self.client.post('/', {'email': self.user.email, 'password': GOOD_PASSWORD})
                self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
                self.assertEqual(urlopen.call_count, 0)
                self.client.logout()

    def test_the_widget_and_script_load_only_for_a_selected_provider_while_password_sign_in_is_on(self):
        cases = [(provider, True, path) for provider in ('', 'turnstile', 'hcaptcha') for path in ('/', '/password/forgot/')]
        cases += [(provider, False, '/') for provider in ('turnstile', 'hcaptcha')]
        for provider, password, path in cases:
            set_methods(True, password)
            set_captcha(provider)
            html = self.client.get(path).content.decode()
            shown = bool(provider) and password
            with self.subTest(provider=provider, password=password, path=path):
                self.assertEqual('id="captchaScript"' in html, shown)
                for name in KEYS:
                    self.assertEqual(f'data-sitekey="{KEYS[name]["site_key"]}"' in html, shown and name == provider)

    def test_only_the_two_forms_allow_the_provider_frames(self):
        expected = 'https://challenges.cloudflare.com https://hcaptcha.com https://*.hcaptcha.com'
        self.assertEqual(frame_sources(self.client.get('/')), expected)
        self.assertEqual(frame_sources(self.client.get('/password/forgot/')), expected)
        self.client.force_login(self.user)
        self.assertEqual(frame_sources(self.client.get('/dashboard/')), None)


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED, CAPTCHA_KEYS=KEYS)
class CaptchaForgotPasswordTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)
        self.user = UserFactory(email='captcha-forgot@example.com')

    def test_the_link_is_sent_only_after_the_provider_confirms_the_token(self):
        for provider in KEYS:
            set_captcha(provider)
            with self.subTest(provider=provider):
                mail.outbox = []
                with patch(URLOPEN, side_effect=answer(False)):
                    response = self.client.post('/password/forgot/', {'email': self.user.email, TOKEN_FIELDS[provider]: 'token'})
                self.assertTemplateUsed(response, 'accounts/forgot_password.html')
                self.assertEqual(messages_of(response), ['The verification failed. Try again.'])
                self.assertEqual(mail.outbox, [])
                with patch(URLOPEN, side_effect=answer(True)):
                    response = self.client.post('/password/forgot/', {'email': self.user.email, TOKEN_FIELDS[provider]: 'token'})
                self.assertTemplateUsed(response, 'accounts/forgot_sent.html')
                self.assertEqual(len(mail.outbox), 1)
