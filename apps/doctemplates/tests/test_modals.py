from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.doctemplates.factories import TemplateAttributeFactory, TemplateFactory, TemplateSectionFactory

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class TemplateEditorModalTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('modal', args=['template_editor'])

    def test_create_mode_for_a_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-modal-name="template_editor"', html)
        self.assertIn('Create Template', html)
        self.assertIn(f'action="{reverse("template_create")}"', html)
        self.assertIn('data-modal-form', html)
        self.assertIn('csrfmiddlewaretoken', html)
        self.assertIn('id="sectionItemTemplate"', html)
        self.assertIn('id="attributeRowTemplate"', html)
        self.assertNotIn('class="section-item" data-section-id="', html.split('id="sectionTree"')[1].split('<template')[0])

    def test_viewer_cannot_open_the_editor(self):
        self.client.force_login(ViewerUserFactory())
        response = self.client.get(self.url, **AJAX)
        self.assertEqual(response.status_code, 403)

    def test_edit_mode_renders_the_template_sections_and_attributes(self):
        tmpl = TemplateFactory(created_by=self.user, name='Mine', description='Own one', is_builtin=False)
        parent = TemplateSectionFactory(template=tmpl, number='1', title='Introduction', parent=None, description='Why')
        TemplateSectionFactory(template=tmpl, number='1.1', title='Purpose', parent=parent)
        TemplateAttributeFactory(template=tmpl, name='Risk Level', field_type='dropdown', options=['Low', 'High'])
        self.client.force_login(self.user)
        response = self.client.get(self.url, {'template': tmpl.public_key}, **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Edit Template', html)
        self.assertIn(f'action="{reverse("template_edit", args=[tmpl.public_key])}"', html)
        self.assertIn('value="Mine"', html)
        self.assertIn('Own one', html)
        self.assertIn('value="Introduction"', html)
        self.assertIn('value="Purpose"', html)
        self.assertIn('>Why</textarea>', html)
        self.assertIn(f'data-section-id="{parent.pk}"', html)
        self.assertIn('value="Risk Level"', html)
        self.assertIn('value="Low, High"', html)
        self.assertIn('<option value="dropdown" selected>', html)

    def test_edit_mode_refuses_a_builtin_a_strangers_private_template_and_admits_an_admin(self):
        builtin = TemplateFactory(is_builtin=True, name='Built')
        other = TemplateFactory(created_by=UserFactory(), is_builtin=False, name='Theirs')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {'template': builtin.public_key}, **AJAX).status_code, 403)
        self.assertEqual(self.client.get(self.url, {'template': other.public_key}, **AJAX).status_code, 403)
        self.client.force_login(AdminUserFactory())
        self.assertEqual(self.client.get(self.url, {'template': other.public_key}, **AJAX).status_code, 200)

    def test_bad_keys_are_not_found(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {'template': 'not-a-key'}, **AJAX).status_code, 404)
        self.assertEqual(self.client.get(self.url, {'template': '00000000-0000-7000-8000-000000000000'}, **AJAX).status_code, 404)


class TemplateImportModalTest(TestCase):

    def test_viewer_cannot_open_the_import_dialog(self):
        self.client.force_login(ViewerUserFactory())
        response = self.client.get(reverse('modal', args=['template_import']), **AJAX)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('data-modal-name="template_import"', response.content.decode())


class TemplateViewModalTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('modal', args=['template_view'])
        self.tmpl = TemplateFactory(is_builtin=True, name='Shared Outline')
        parent = TemplateSectionFactory(template=self.tmpl, number='1', title='Introduction', parent=None, description='Overview section')
        TemplateSectionFactory(template=self.tmpl, number='1.1', title='Purpose', parent=parent)
        TemplateAttributeFactory(template=self.tmpl, name='Risk Level', field_type='dropdown', options=['Low', 'Medium', 'High'])

    def test_renders_the_tree_attributes_and_duplicate_form(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {'template': self.tmpl.public_key}, **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-modal-name="template_view"', html)
        self.assertIn('Shared Outline', html)
        self.assertIn('Introduction', html)
        self.assertIn('Purpose', html)
        self.assertIn('Overview section', html)
        self.assertIn('Risk Level', html)
        self.assertEqual(html.count('<ul class="view-section-tree">'), 2)
        self.assertIn(f'action="{reverse("template_duplicate", args=[self.tmpl.public_key])}"', html)
        self.assertIn('data-confirm="A private copy named &quot;Shared Outline (Copy)&quot; will be created."', html)

    def test_requires_the_template_parameter(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, **AJAX).status_code, 404)

    def test_private_template_of_another_user_is_refused_without_a_leak(self):
        other = TemplateFactory(is_builtin=False, is_global=False, name='Top Secret Methodology', created_by=UserFactory())
        self.client.force_login(self.user)
        response = self.client.get(self.url, {'template': other.public_key}, **AJAX)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('Top Secret Methodology', response.content.decode())

    def test_global_own_and_admin_cases_are_admitted(self):
        other_user = UserFactory()
        shared = TemplateFactory(is_builtin=False, is_global=True, name='Shared Template', created_by=other_user)
        private = TemplateFactory(is_builtin=False, is_global=False, name='Secret', created_by=other_user)
        own = TemplateFactory(is_builtin=False, is_global=False, name='MyPrivate', created_by=self.user)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {'template': shared.public_key}, **AJAX).status_code, 200)
        self.assertEqual(self.client.get(self.url, {'template': own.public_key}, **AJAX).status_code, 200)
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url, {'template': private.public_key}, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Secret', response.content.decode())

    def test_viewer_sees_no_duplicate_form(self):
        self.client.force_login(ViewerUserFactory())
        response = self.client.get(self.url, {'template': self.tmpl.public_key}, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('viewTemplateDuplicateForm', response.content.decode())
