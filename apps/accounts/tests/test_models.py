from django.test import TestCase

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory


class UserModelTest(TestCase):

    def test_is_system_admin_property(self):
        admin = AdminUserFactory()
        regular = UserFactory()
        viewer = ViewerUserFactory()
        self.assertTrue(admin.is_system_admin)
        self.assertFalse(regular.is_system_admin)
        self.assertFalse(viewer.is_system_admin)

    def test_is_viewer_property(self):
        viewer = ViewerUserFactory()
        regular = UserFactory()
        self.assertTrue(viewer.is_viewer)
        self.assertFalse(regular.is_viewer)

    def test_str_display_name(self):
        user = UserFactory(display_name='Test User', first_name='Test', last_name='User')
        self.assertEqual(str(user), 'Test User')

    def test_str_full_name(self):
        user = UserFactory(display_name='', first_name='John', last_name='Doe')
        self.assertEqual(str(user), 'John Doe')

    def test_str_email_fallback(self):
        user = UserFactory(display_name='', first_name='', last_name='', email='test@example.com')
        self.assertEqual(str(user), 'test@example.com')

    def test_get_initials(self):
        user = UserFactory(first_name='Erin', last_name='Nolan')
        self.assertEqual(user.get_initials(), 'EN')

    def test_get_initials_email_fallback(self):
        user = UserFactory(first_name='', last_name='', email='test@example.com')
        self.assertEqual(user.get_initials(), 'TE')
