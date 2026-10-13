from urllib.parse import urlsplit

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.emails import send_invitation_email, send_password_link_email
from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.models import User
from apps.accounts.tests.test_auth_methods import messages_of, set_methods
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.accounts.tests.test_password_views import FAILING_BACKEND, NEW_PASSWORD, user_with_password
from apps.core.keys import uuid7

INVITEE = 'invitee@example.com'


def emailed_link(message):
    return next(line for line in message.body.splitlines() if line.startswith('http://testserver/password/set/'))


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class InviteViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def invite(self, email=INVITEE):
        return self.client.post('/admin-panel/invite-user/', {
            'email': email, 'first_name': 'In', 'last_name': 'Vitee', 'system_role': 'user',
        })

    def test_with_password_on_the_email_carries_the_link_and_the_microsoft_paragraph(self):
        set_methods(True, True)
        response = self.invite()
        self.assertRedirects(response, '/admin-panel/?tab=users', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), [f'Invitation sent to {INVITEE}.'])
        user = User.objects.get(email=INVITEE)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [INVITEE])
        self.assertTrue(message.subject.startswith('ArcSpec - '))
        self.assertIn(str(self.admin), message.body)
        self.assertIn('http://testserver/password/set/', message.body)
        self.assertIn('Microsoft account', message.body)
        self.assertIn('http://testserver/password/set/', message.alternatives[0].content)
        self.assertIn('Microsoft account', message.alternatives[0].content)

    def test_with_password_off_the_email_has_no_link(self):
        self.invite()
        message = mail.outbox[0]
        self.assertNotIn('/password/set/', message.body)
        self.assertNotIn('/password/set/', message.alternatives[0].content)
        self.assertIn('Microsoft account', message.body)

    def test_with_microsoft_off_the_email_has_no_microsoft_paragraph(self):
        set_methods(False, True)
        self.invite()
        message = mail.outbox[0]
        self.assertIn('/password/set/', message.body)
        self.assertNotIn('Microsoft account', message.body)
        self.assertNotIn('Microsoft account', message.alternatives[0].content)

    def test_the_link_opens_the_set_password_page_and_the_chosen_password_signs_in(self):
        set_methods(True, True)
        self.invite()
        path = urlsplit(emailed_link(mail.outbox[0])).path
        self.client.logout()
        self.assertTemplateUsed(self.client.get(path), 'accounts/set_password.html')
        response = self.client.post(path, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.client.post('/', {'email': INVITEE, 'password': NEW_PASSWORD})
        self.assertEqual(self.client.session['_auth_user_id'], str(User.objects.get(email=INVITEE).pk))

    @override_settings(EMAIL_BACKEND=FAILING_BACKEND)
    def test_a_mail_failure_keeps_the_user_and_warns(self):
        with self.assertLogs('apps.administration.views', level='ERROR') as logs:
            response = self.invite()
        self.assertTrue(User.objects.filter(email=INVITEE).exists())
        self.assertEqual(len(messages_of(response)), 1)
        self.assertIn('could not be sent', messages_of(response)[0])
        self.assertIn('mail server unreachable', logs.output[0])

    def test_a_refused_form_sends_nothing(self):
        UserFactory(email=INVITEE)
        self.invite()
        self.assertEqual(mail.outbox, [])

    def test_no_email_contains_a_password(self):
        set_methods(True, True)
        self.invite()
        path = urlsplit(emailed_link(mail.outbox[0])).path
        self.client.logout()
        self.client.post(path, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.client.post('/password/forgot/', {'email': INVITEE})
        self.assertEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertNotIn(NEW_PASSWORD, message.body)
            self.assertNotIn(NEW_PASSWORD, message.alternatives[0].content)


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class ResendInvitationTest(TestCase):

    def setUp(self):
        set_methods(True, True)
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)
        self.invitee = UserFactory(email=INVITEE)
        self.invitee.set_unusable_password()
        self.invitee.save()

    def resend(self, user):
        return self.client.post(f'/admin-panel/resend-invitation/{user.public_key}/')

    def test_sends_the_email_again_for_a_user_without_a_password(self):
        response = self.resend(self.invitee)
        self.assertRedirects(response, '/admin-panel/?tab=users', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), [f'Invitation sent to {INVITEE}.'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('http://testserver/password/set/', mail.outbox[0].body)

    def test_refuses_for_a_user_with_a_password(self):
        user = user_with_password(email='haspass@example.com')
        response = self.resend(user)
        self.assertEqual(mail.outbox, [])
        self.assertIn('already has a password', messages_of(response)[0])

    def test_refuses_for_a_deactivated_user(self):
        self.invitee.is_active = False
        self.invitee.save()
        response = self.resend(self.invitee)
        self.assertEqual(mail.outbox, [])
        self.assertIn('deactivated', messages_of(response)[0])

    def test_refuses_for_a_user_who_has_signed_in(self):
        self.invitee.last_login = timezone.now()
        self.invitee.save()
        response = self.resend(self.invitee)
        self.assertEqual(mail.outbox, [])
        self.assertIn('already signed in', messages_of(response)[0])

    def test_non_admin_gets_403(self):
        self.client.force_login(UserFactory())
        self.assertEqual(self.resend(self.invitee).status_code, 403)
        self.assertEqual(mail.outbox, [])

    def test_unknown_user_is_404(self):
        self.assertEqual(self.client.post(f'/admin-panel/resend-invitation/{uuid7()}/').status_code, 404)
        self.assertEqual(self.client.post('/admin-panel/resend-invitation/999999/').status_code, 404)

    @override_settings(EMAIL_BACKEND=FAILING_BACKEND)
    def test_a_mail_failure_warns(self):
        with self.assertLogs('apps.administration.views', level='ERROR'):
            response = self.resend(self.invitee)
        self.assertIn('could not be sent', messages_of(response)[0])


class EmailContentTest(TestCase):

    def setUp(self):
        self.user = UserFactory(email=INVITEE, first_name='In')
        self.request = RequestFactory().get('/')

    def test_invitation_subject_body_and_html(self):
        send_invitation_email(
            user=self.user, inviter='An Admin', site_url='http://testserver/',
            link_url='http://testserver/password/set/MQ/abc-def/', entra=True,
        )
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'ArcSpec - Invitation')
        self.assertEqual(message.to, [INVITEE])
        for content in (message.body, message.alternatives[0].content):
            self.assertIn('An Admin', content)
            self.assertIn('http://testserver/password/set/MQ/abc-def/', content)
            self.assertIn('http://testserver/', content)
            self.assertIn('1 day', content)

    def test_invitation_without_either_method_tells_the_invitee_to_ask(self):
        send_invitation_email(
            user=self.user, inviter='An Admin', site_url='http://testserver/',
            link_url=None, entra=False,
        )
        self.assertIn('Ask your administrator', mail.outbox[0].body)

    def test_password_link_subject_body_and_html(self):
        send_password_link_email(self.user, 'http://testserver/password/set/MQ/abc-def/')
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'ArcSpec - Set your password')
        for content in (message.body, message.alternatives[0].content):
            self.assertIn('http://testserver/password/set/MQ/abc-def/', content)
            self.assertIn('ignore this email', content)
