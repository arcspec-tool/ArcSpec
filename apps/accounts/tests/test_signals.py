from django.test import TestCase

from apps.accounts.factories import UserFactory
from apps.accounts.models import UserSettings


class UserSettingsSignalTest(TestCase):

    def test_user_settings_created_on_user_creation(self):
        user = UserFactory()
        self.assertTrue(UserSettings.objects.filter(user=user).exists())
        settings = user.settings
        self.assertIsNotNone(settings)
