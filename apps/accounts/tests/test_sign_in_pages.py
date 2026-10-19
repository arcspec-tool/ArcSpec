from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.accounts.factories import UserFactory
from apps.accounts.tests.test_auth_methods import messages_of, set_methods
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.accounts.tests.test_password_views import AJAX, GOOD_PASSWORD, input_tag, link_path, user_with_password


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class SentPageTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)

    @override_settings(PASSWORD_RESET_TIMEOUT=172800)
    def test_the_sent_page_states_the_link_lifetime_from_the_settings(self):
        response = self.client.post('/password/forgot/', {'email': 'nobody@example.com'})
        self.assertContains(response, 'expires in 2 days.')


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class SignInFocusTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)
        self.user = user_with_password(email='focus@example.com')

    def test_a_fresh_page_focuses_the_address(self):
        html = self.client.get('/').content.decode()
        self.assertIn('autofocus', input_tag(html, 'email'))
        self.assertNotIn('autofocus', input_tag(html, 'password'))
        self.assertIn('autocomplete="username"', input_tag(html, 'email'))

    def test_a_failed_attempt_keeps_the_address_and_focuses_the_password(self):
        response = self.client.post('/', {'email': self.user.email, 'password': 'wrong-password-xyz'})
        self.assertEqual(messages_of(response), ['Incorrect email address or password.'])
        html = response.content.decode()
        self.assertIn(f'value="{self.user.email}"', input_tag(html, 'email'))
        self.assertNotIn('autofocus', input_tag(html, 'email'))
        self.assertIn('autofocus', input_tag(html, 'password'))
        self.assertNotIn('value=', input_tag(html, 'password'))

    def test_a_throttled_attempt_keeps_the_address(self):
        for _ in range(5):
            self.client.post('/', {'email': self.user.email, 'password': 'wrong-password-xyz'})
        response = self.client.post('/', {'email': self.user.email, 'password': GOOD_PASSWORD})
        self.assertEqual(messages_of(response), ['Too many attempts. Try again in a few minutes.'])
        self.assertIn(f'value="{self.user.email}"', input_tag(response.content.decode(), 'email'))


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class PasswordFieldTest(TestCase):

    def setUp(self):
        cache.clear()
        set_methods(True, True)

    def assert_toggle(self, html, field_id):
        self.assertIn(f'data-password-toggle aria-controls="{field_id}"', html)

    def test_every_password_input_has_a_toggle(self):
        user = user_with_password(email='toggle@example.com')
        self.assert_toggle(self.client.get('/').content.decode(), 'id_password')
        html = self.client.get(link_path(user)).content.decode()
        for field_id in ('id_new_password1', 'id_new_password2'):
            self.assert_toggle(html, field_id)
        self.client.force_login(user)
        html = self.client.get('/modals/change_password/', **AJAX).content.decode()
        for field_id in ('id_old_password', 'id_new_password1', 'id_new_password2'):
            self.assert_toggle(html, field_id)

    def test_the_rules_and_the_errors_are_tied_to_their_inputs(self):
        user = UserFactory(email='rules@example.com')
        html = self.client.get(link_path(user)).content.decode()
        first = input_tag(html, 'new_password1')
        self.assertIn('aria-describedby="id_new_password1_helptext"', first)
        self.assertNotIn('aria-invalid', first)
        self.assertIn('id="id_new_password1_helptext"', html)
        response = self.client.post(link_path(user), {'new_password1': 'staple-garden-lamp', 'new_password2': 'staple-garden-lampx'})
        html = response.content.decode()
        second = input_tag(html, 'new_password2')
        self.assertIn('aria-describedby="id_new_password2_error"', second)
        self.assertIn('aria-invalid="true"', second)
        self.assertIn('id="id_new_password2_error"', html)
        self.assertNotIn('aria-invalid', input_tag(html, 'new_password1'))

    def test_a_forgot_error_is_tied_to_the_address(self):
        response = self.client.post('/password/forgot/', {'email': 'not-an-address'})
        html = response.content.decode()
        self.assertIn('aria-invalid="true"', input_tag(html, 'email'))
        self.assertIn('aria-describedby="id_email_error"', input_tag(html, 'email'))
        self.assertIn('id="id_email_error"', html)
