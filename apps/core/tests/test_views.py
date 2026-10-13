from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase


class HealthViewTest(TestCase):

    def test_returns_ok_when_database_answers(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_returns_503_when_database_fails(self):
        with patch('apps.core.views.connection') as mock_connection:
            mock_connection.cursor.side_effect = DatabaseError('down')
            response = self.client.get('/health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'error')

    def test_rejects_post(self):
        response = self.client.post('/health/')
        self.assertEqual(response.status_code, 405)

    def test_is_not_cached(self):
        response = self.client.get('/health/')
        self.assertIn('no-cache', response['Cache-Control'])
