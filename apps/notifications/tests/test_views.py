from django.test import TestCase

from apps.core.keys import uuid7

from apps.accounts.factories import UserFactory
from apps.notifications.factories import NotificationFactory


class NotificationMarkReadViewTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_unauthenticated_returns_403(self):
        self.client.logout()
        notification = NotificationFactory(user=self.user)
        response = self.client.post(f'/api/notifications/{notification.public_key}/read/')
        self.assertEqual(response.status_code, 403)

    def test_mark_own_notification_read(self):
        notification = NotificationFactory(user=self.user, is_read=False)
        response = self.client.post(f'/api/notifications/{notification.public_key}/read/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_returns_unread_count(self):
        NotificationFactory(user=self.user, is_read=False)
        n2 = NotificationFactory(user=self.user, is_read=False)
        response = self.client.post(f'/api/notifications/{n2.public_key}/read/')
        data = response.json()
        self.assertEqual(data['unread_count'], 1)

    def test_cannot_mark_other_user_notification(self):
        other_user = UserFactory()
        notification = NotificationFactory(user=other_user, is_read=False)
        response = self.client.post(f'/api/notifications/{notification.public_key}/read/')
        self.assertEqual(response.status_code, 404)

    def test_mark_nonexistent_notification(self):
        response = self.client.post(f'/api/notifications/{uuid7()}/read/')
        self.assertEqual(response.status_code, 404)


class NotificationMarkAllReadViewTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_unauthenticated_returns_403(self):
        self.client.logout()
        response = self.client.post('/api/notifications/read-all/')
        self.assertEqual(response.status_code, 403)

    def test_mark_all_read(self):
        NotificationFactory(user=self.user, is_read=False)
        NotificationFactory(user=self.user, is_read=False)
        NotificationFactory(user=self.user, is_read=False)
        response = self.client.post('/api/notifications/read-all/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['unread_count'], 0)

    def test_does_not_affect_other_users(self):
        other_user = UserFactory()
        NotificationFactory(user=other_user, is_read=False)
        self.client.post('/api/notifications/read-all/')
        from apps.notifications.models import Notification
        self.assertEqual(
            Notification.objects.filter(user=other_user, is_read=False).count(), 1
        )
