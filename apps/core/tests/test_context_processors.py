from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.factories import UserFactory
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.administration.models import SystemSettings
from apps.core.context_processors import system_settings, unread_notification_count
from apps.notifications.factories import NotificationFactory


class UnreadNotificationCountTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def test_authenticated_user_with_notifications(self):
        user = UserFactory()
        NotificationFactory(user=user, is_read=False)
        NotificationFactory(user=user, is_read=True)
        request = self.factory.get('/')
        request.user = user
        result = unread_notification_count(request)
        self.assertEqual(result['unread_notification_count'], 1)

    def test_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/')
        request.user = AnonymousUser()
        result = unread_notification_count(request)
        self.assertEqual(result['unread_notification_count'], 0)


class SystemSettingsContextProcessorTest(TestCase):

    def test_returns_settings(self):
        request = RequestFactory().get('/')
        result = system_settings(request)
        self.assertEqual(result['system_settings'], SystemSettings.load())

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
    def test_returns_the_effective_auth_methods_from_the_same_row(self):
        stored = SystemSettings.load()
        stored.password_login_enabled = True
        stored.save()
        request = RequestFactory().get('/')
        result = system_settings(request)
        self.assertEqual(result['auth_methods'], (True, True))
        self.assertIs(result['system_settings'], request._system_settings)
        with self.assertNumQueries(0):
            self.assertEqual(system_settings(request)['auth_methods'], (True, True))
