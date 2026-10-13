import os
import runpy
from unittest.mock import patch

import environ
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

BASE_SETTINGS = settings.BASE_DIR / 'config' / 'settings' / 'base.py'

DATABASE_KEYS = ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD')


def load_base_settings():
    return runpy.run_path(str(BASE_SETTINGS))


class DatabaseSettingsTest(SimpleTestCase):

    def test_each_postgres_key_is_required(self):
        for key in DATABASE_KEYS:
            with self.subTest(key=key):
                with patch.dict(os.environ), patch.object(environ.Env, 'read_env'):
                    os.environ.pop(key, None)
                    with self.assertRaises(ImproperlyConfigured) as raised:
                        load_base_settings()
                self.assertIn(key, str(raised.exception))

    def test_database_url_is_not_read(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgres://other:other@elsewhere:1/other'}), \
                patch.object(environ.Env, 'read_env'):
            loaded = load_base_settings()
        self.assertEqual(loaded['DATABASES']['default']['HOST'], 'db')
        self.assertEqual(loaded['DATABASES']['default']['NAME'], os.environ['POSTGRES_DB'])
