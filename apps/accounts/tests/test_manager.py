import os
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.accounts.factories import UserFactory
from apps.accounts.models import User

EMAIL = 'first.admin@example.com'


class UserManagerTest(TestCase):

    def test_createsuperuser_makes_a_system_administrator(self):
        with patch.dict(os.environ, {'DJANGO_SUPERUSER_PASSWORD': 'a-long-password-1'}):
            call_command('createsuperuser', email=EMAIL, interactive=False, verbosity=0)
        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.system_role, 'admin')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password('a-long-password-1'))

    def test_create_user_defaults_to_the_user_role(self):
        user = User.objects.create_user('Someone@Example.COM', 'a-long-password-1')
        self.assertEqual(user.system_role, 'user')
        self.assertFalse(user.is_staff)
        self.assertEqual(user.email, 'Someone@example.com')

    def test_create_user_refuses_an_empty_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user('', 'a-long-password-1')


class CreateAdminCommandTest(TestCase):

    def test_creates_an_administrator_and_prints_the_generated_password(self):
        out = StringIO()
        call_command('create_admin', EMAIL, stdout=out)
        password = [line for line in out.getvalue().splitlines() if line.startswith('Password: ')][0][10:]
        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.system_role, 'admin')
        self.assertGreaterEqual(len(password), 20)
        self.assertTrue(user.check_password(password))

    def test_refuses_once_any_account_exists(self):
        UserFactory(email='someone@example.com')
        with self.assertRaises(CommandError):
            call_command('create_admin', EMAIL, stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)
