from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class ModalEndpointTest(TestCase):

    def setUp(self):
        self.user = UserFactory()

    def test_anonymous_is_sent_to_sign_in(self):
        response = self.client.get(reverse('modal', args=['sign_out']), **AJAX)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(response['X-Redirect-To'].startswith('/?next='))
        self.assertEqual(response.content, b'')

    def test_request_without_the_ajax_header_is_not_found(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['sign_out']))
        self.assertEqual(response.status_code, 404)

    def test_unknown_name_is_not_found(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['no-such-modal']), **AJAX)
        self.assertEqual(response.status_code, 404)

    def test_response_is_never_cached(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['sign_out']), **AJAX)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn('X-Requested-With', response['Vary'])

    def test_sign_out_renders_the_one_logout_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['sign_out']), **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(html.count('id="signOutModal"'), 1)
        self.assertEqual(html.count('action="/logout/"'), 1)
        self.assertIn('csrfmiddlewaretoken', html)
        self.assertIn('data-modal-name="sign_out"', html)

    def test_confirm_renders_its_parameters_as_text(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['confirm']), {
            'title': 'Delete <b>row</b>',
            'message': 'Really? <script>alert(1)</script>',
            'confirm_label': 'Delete',
            'variant': 'warning',
        }, **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Delete &lt;b&gt;row&lt;/b&gt;', html)
        self.assertIn('Really? &lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertIn('class="btn btn-warning" id="confirmModalConfirm" data-modal-confirm>Delete<', html)
        self.assertIn('bi-exclamation-triangle text-warning', html)

    def test_confirm_defaults(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['confirm']), {'variant': 'success'}, **AJAX)
        html = response.content.decode()
        self.assertIn('>Confirm<', html)
        self.assertIn('Are you sure?', html)
        self.assertIn('class="btn btn-danger" id="confirmModalConfirm"', html)
        self.assertIn('bi-exclamation-triangle text-danger', html)

    def test_undeclared_parameters_are_ignored(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('modal', args=['confirm']), {'title': 'T', 'evil': '<x>'}, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<x>', response.content.decode())
        self.assertNotIn('&lt;x&gt;', response.content.decode())


class ModalRegistryTest(TestCase):

    def test_every_modal_without_parameters_renders_for_a_signed_in_user(self):
        self.client.force_login(UserFactory())
        for name in ('confirm', 'sign_out', 'edit_profile', 'project_create', 'template_editor'):
            response = self.client.get(reverse('modal', args=[name]), **AJAX)
            self.assertEqual(response.status_code, 200, name)
            self.assertIn(f'data-modal-name="{name}"', response.content.decode())


class PagesCarryNoModalMarkupTest(TestCase):

    def test_signed_in_page_has_the_targets_and_no_sign_out_or_confirm_markup(self):
        self.client.force_login(UserFactory())
        html = self.client.get('/profile/').content.decode()
        self.assertEqual(html.count('id="modalTarget"'), 1)
        self.assertEqual(html.count('id="confirmTarget"'), 1)
        self.assertNotIn('id="signOutModal"', html)
        self.assertNotIn('id="confirmModal"', html)
        self.assertNotIn('action="/logout/"', html)
        self.assertEqual(html.count('data-modal-open="sign_out"'), 2)
