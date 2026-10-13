from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.models import User
from apps.projects.models import Tag

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class AdministrationModalsTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.user = UserFactory(first_name='Plain', last_name='Member', system_role='user')

    def test_the_three_modals_are_for_administrators_only(self):
        for name, params in (('invite_user', {}), ('edit_role', {'user': str(self.user.public_key)}), ('tag_preset', {})):
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), params, **AJAX).status_code, 403, name)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), params, **AJAX).status_code, 200, name)

    def test_the_panel_carries_triggers_and_no_modal_markup(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_panel'))
        html = response.content.decode()
        self.assertNotIn('modal fade', html)
        self.assertNotIn('data-bs-toggle="modal"', html)
        self.assertNotIn('data-user-id=', html)
        self.assertIn('data-modal-open="invite_user"', html)
        self.assertIn(f'data-modal-open="edit_role" data-user="{self.user.public_key}"', html)
        self.assertNotIn(f'data-modal-open="edit_role" data-user="{self.admin.public_key}"', html)
        self.assertNotIn('invite_form', response.context)
        html = self.client.get(reverse('admin_panel'), {'tab': 'tags'}).content.decode()
        self.assertIn('data-modal-open="tag_preset"', html)
        self.assertNotIn('modal fade', html)

    def test_edit_role_refuses_the_signed_in_administrator(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('modal', args=['edit_role']), {'user': str(self.admin.public_key)}, **AJAX)
        self.assertEqual(response.status_code, 403)

    def test_invite_user_renders_the_form_and_answers_an_invalid_post_with_422(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('modal', args=['invite_user']), **AJAX).content.decode()
        self.assertIn('id="inviteUserModal"', html)
        self.assertIn(f'action="{reverse("admin_invite_user")}"', html)
        self.assertIn('data-modal-form', html)
        self.assertNotIn('name="system_role"', html)
        self.assertIn('created with the User role', html)
        response = self.client.post(reverse('admin_invite_user'), {
            'email': 'not-an-address',
            'first_name': 'Typed',
            'last_name': '',
        }, **AJAX)
        self.assertEqual(response.status_code, 422)
        html = response.content.decode()
        self.assertIn('data-modal-name="invite_user"', html)
        self.assertIn('Enter a valid email address.', html)
        self.assertIn('value="Typed"', html)
        self.assertFalse(User.objects.filter(first_name='Typed').exists())

    def test_edit_role_is_prefilled_from_the_key_and_answers_an_invalid_post_with_422(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('modal', args=['edit_role']), {'user': str(self.user.public_key)}, **AJAX)
        html = response.content.decode()
        self.assertIn('id="editRoleModal"', html)
        self.assertIn('Plain Member', html)
        self.assertIn(f'action="{reverse("admin_edit_role", args=[self.user.public_key])}"', html)
        self.assertIn('<option value="user" selected>', html)
        self.assertEqual(self.client.get(reverse('modal', args=['edit_role']), **AJAX).status_code, 404)
        self.assertEqual(self.client.get(reverse('modal', args=['edit_role']), {'user': 'nope'}, **AJAX).status_code, 404)
        response = self.client.post(reverse('admin_edit_role', args=[self.user.public_key]), {'system_role': 'emperor'}, **AJAX)
        self.assertEqual(response.status_code, 422)
        self.assertIn('data-modal-name="edit_role"', response.content.decode())
        self.user.refresh_from_db()
        self.assertEqual(self.user.system_role, 'user')

    def test_tag_preset_renders_the_form_and_answers_an_invalid_post_with_422(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('modal', args=['tag_preset']), **AJAX).content.decode()
        self.assertIn('id="tagPresetModal"', html)
        self.assertIn(f'action="{reverse("admin_tag_preset_create")}"', html)
        self.assertIn('name="name"', html)
        response = self.client.post(reverse('admin_tag_preset_create'), {'name': '', 'color': '#123456'}, **AJAX)
        self.assertEqual(response.status_code, 422)
        self.assertIn('data-modal-name="tag_preset"', response.content.decode())
        self.assertIn('This field is required.', response.content.decode())
        self.assertEqual(Tag.objects.filter(project__isnull=True, color='#123456').count(), 0)
