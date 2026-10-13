from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.doctemplates.models import Template

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

VALID_TEMPLATE = {
    'name': 'Posted From A Modal',
    'doc_type': 'requirements',
    'sections-TOTAL_FORMS': '0',
    'sections-INITIAL_FORMS': '0',
    'sections-MIN_NUM_FORMS': '0',
    'sections-MAX_NUM_FORMS': '1000',
}


class AjaxRedirectMiddlewareTest(TestCase):

    def test_a_redirect_answered_to_an_ajax_request_becomes_204_with_the_target(self):
        self.client.force_login(UserFactory())
        response = self.client.post(reverse('template_create'), VALID_TEMPLATE, **AJAX)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['X-Redirect-To'], reverse('template_list'))
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTrue(Template.objects.filter(name='Posted From A Modal').exists())

    def test_the_message_survives_for_the_page_the_browser_loads_next(self):
        self.client.force_login(UserFactory())
        self.client.post(reverse('template_create'), VALID_TEMPLATE, **AJAX)
        page = self.client.get(reverse('template_list'))
        self.assertContains(page, 'created.')

    def test_a_plain_request_keeps_its_redirect(self):
        self.client.force_login(UserFactory())
        response = self.client.post(reverse('template_create'), VALID_TEMPLATE)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('template_list'))

    def test_an_anonymous_ajax_request_is_sent_to_sign_in(self):
        response = self.client.get(reverse('modal', args=['sign_out']), **AJAX)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(response['X-Redirect-To'].startswith('/?next='))
