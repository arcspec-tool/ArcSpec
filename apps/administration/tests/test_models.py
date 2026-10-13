from django.test import TestCase

from apps.administration.models import SystemSettings


class SystemSettingsModelTest(TestCase):

    def test_load_creates_singleton(self):
        settings = SystemSettings.load()
        self.assertEqual(settings.pk, 1)
        self.assertEqual(str(settings), 'System Settings')

    def test_load_returns_existing(self):
        s1 = SystemSettings.load()
        s1.org_name = 'Custom Name'
        s1.save()
        s2 = SystemSettings.load()
        self.assertEqual(s2.org_name, 'Custom Name')
        self.assertEqual(SystemSettings.objects.count(), 1)

    def test_save_forces_pk_1(self):
        s = SystemSettings(pk=99)
        s.save()
        self.assertEqual(s.pk, 1)
        self.assertEqual(SystemSettings.objects.count(), 1)
