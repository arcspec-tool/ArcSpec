import re

from django.core import mail
from django.test import TestCase, override_settings

from apps.accounts.emails import send_invitation_email, send_password_link_email
from apps.accounts.factories import UserFactory
from apps.notifications.factories import AuditLogFactory, NotificationFactory
from apps.notifications.jobs import send_email_notification, send_weekly_digest
from apps.projects.factories import OwnedProjectFactory

SITE = 'https://arcspec.example'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_URL=SITE)
class EmailLayoutTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.user.settings.notify_status_changes = True
        self.user.settings.notify_weekly_digest = True
        self.user.settings.save()
        self.project = OwnedProjectFactory(created_by=self.user)

    def send_all(self):
        link = f'{SITE}/password/set/key/token/'
        send_invitation_email(self.user, 'An Admin', f'{SITE}/', link, True)
        send_password_link_email(self.user, link)
        send_email_notification(NotificationFactory(
            user=self.user, project=self.project, type='status_changed',
            message='REQ-001 status changed', link=self.project.get_absolute_url(),
        ))
        AuditLogFactory(project=self.project, user=self.user, action='created', target_type='Item', target_id='REQ-001')
        send_weekly_digest()
        return mail.outbox

    def test_every_email_embeds_its_two_images(self):
        messages = self.send_all()
        self.assertEqual(len(messages), 4)
        for message in messages:
            with self.subTest(subject=message.subject):
                sources = re.findall(r'<img[^>]+src="([^"]*)"', message.alternatives[0].content)
                self.assertEqual(len(sources), 2)
                for source in sources:
                    self.assertTrue(source.startswith('data:image/png;base64,'), source[:40])

    def test_notification_and_digest_links_use_the_site_url(self):
        notification, digest = self.send_all()[2:]
        project_url = f'{SITE}{self.project.get_absolute_url()}'
        settings_url = f'{SITE}/settings/#notifications'
        self.assertIn(f'href="{project_url}"', notification.alternatives[0].content)
        self.assertIn(f'href="{settings_url}"', notification.alternatives[0].content)
        self.assertIn(f'View in ArcSpec: {project_url}', notification.body)
        self.assertIn(f'href="{project_url}"', digest.alternatives[0].content)
        self.assertIn(f'href="{SITE}/dashboard/"', digest.alternatives[0].content)
        self.assertIn(f'href="{settings_url}"', digest.alternatives[0].content)
        self.assertIn(project_url, digest.body)
