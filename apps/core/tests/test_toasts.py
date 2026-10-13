import json
import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.doctemplates.models import Template

VALID_TEMPLATE = {
    'name': 'Toast Source',
    'doc_type': 'requirements',
    'sections-TOTAL_FORMS': '0',
    'sections-INITIAL_FORMS': '0',
    'sections-MIN_NUM_FORMS': '0',
    'sections-MAX_NUM_FORMS': '1000',
}


class ToastTest(TestCase):

    def test_django_messages_reach_the_page_as_json_and_not_as_markup(self):
        self.client.force_login(UserFactory())
        self.client.post(reverse('template_create'), VALID_TEMPLATE)
        self.assertTrue(Template.objects.filter(name='Toast Source').exists())
        html = self.client.get(reverse('template_list')).content.decode()
        self.assertNotIn('class="toast ', html)
        match = re.search(r'<script id="page-messages" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1).replace('\\u0022', '"'))
        self.assertEqual(payload, [{'message': 'Template "Toast Source" created.', 'type': 'success'}])

    def test_a_page_without_messages_carries_an_empty_list(self):
        self.client.force_login(UserFactory())
        html = self.client.get(reverse('template_list')).content.decode()
        self.assertIn('<script id="page-messages" type="application/json">[]</script>', html)
        self.assertEqual(html.count('id="toastContainer"'), 1)

    def test_error_messages_map_to_the_danger_type(self):
        self.client.force_login(UserFactory())
        self.client.post(reverse('template_create'), {'name': '', 'doc_type': 'requirements', 'sections-TOTAL_FORMS': '0', 'sections-INITIAL_FORMS': '0', 'sections-MIN_NUM_FORMS': '0', 'sections-MAX_NUM_FORMS': '1000'})
        html = self.client.get(reverse('template_list')).content.decode()
        match = re.search(r'<script id="page-messages" type="application/json">(.*?)</script>', html, re.S)
        payload = json.loads(match.group(1).replace('\\u0022', '"'))
        self.assertEqual(payload, [{'message': 'Please correct the errors below.', 'type': 'danger'}])
