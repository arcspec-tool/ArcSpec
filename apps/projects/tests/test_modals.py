from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory, ViewerUserFactory
from apps.doctemplates.factories import TemplateFactory
from apps.projects.factories import ProjectFactory, ProjectMembershipFactory
from apps.projects.models import Project

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class ProjectListModalsTest(TestCase):

    def setUp(self):
        self.admin = UserFactory()
        self.editor = UserFactory()
        self.stranger = UserFactory()
        self.project = ProjectFactory(name='Keyed Project', color='#198754', status='in-review', description='Edit me')
        ProjectMembershipFactory(project=self.project, user=self.admin, role='admin')
        ProjectMembershipFactory(project=self.project, user=self.editor, role='editor')

    def test_project_create_for_a_user_and_not_for_a_viewer(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('modal', args=['project_create']), **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="newProjectModal"', html)
        self.assertIn(f'action="{reverse("project_create")}"', html)
        self.assertIn('data-modal-form', html)
        self.assertIn('value="#284E8A" checked', html)
        self.assertEqual(html.count('class="color-swatch-label"'), 6)
        self.client.force_login(ViewerUserFactory())
        self.assertEqual(self.client.get(reverse('modal', args=['project_create']), **AJAX).status_code, 403)

    def test_project_edit_is_prefilled_for_an_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('modal', args=['project_edit']), {'project': self.project.slug}, **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="editProjectModal"', html)
        self.assertIn(f'action="{reverse("project_update", args=[self.project.slug])}"', html)
        self.assertIn('value="Keyed Project"', html)
        self.assertIn('Edit me', html)
        self.assertIn('<option value="in-review" selected>', html)
        self.assertIn('value="#198754" checked', html)
        self.assertNotIn('value="#284E8A" checked', html)

    def test_project_edit_and_delete_refuse_an_editor_and_hide_from_a_stranger(self):
        for name in ('project_edit', 'project_delete'):
            self.client.force_login(self.editor)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), {'project': self.project.slug}, **AJAX).status_code, 403, name)
            self.client.force_login(self.stranger)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), {'project': self.project.slug}, **AJAX).status_code, 404, name)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), **AJAX).status_code, 404, name)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), {'project': 'no such/slug'}, **AJAX).status_code, 404, name)

    def test_project_delete_names_the_project_and_posts_to_its_route(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('modal', args=['project_delete']), {'project': self.project.slug}, **AJAX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<strong id="deleteProjectName">Keyed Project</strong>', html)
        self.assertIn(f'action="{reverse("project_delete", args=[self.project.slug])}"', html)
        self.assertIn('csrfmiddlewaretoken', html)

    def test_invalid_create_from_the_modal_returns_the_bound_modal(self):
        self.client.force_login(self.admin)
        private = TemplateFactory(is_builtin=False, is_global=False, created_by=self.stranger)
        response = self.client.post(reverse('project_create'), {
            'name': '',
            'description': 'Kept',
            'template': private.pk,
            'status': 'draft',
            'color': '#dc3545',
        }, **AJAX)
        self.assertEqual(response.status_code, 422)
        html = response.content.decode()
        self.assertIn('data-modal-name="project_create"', html)
        self.assertIn('This field is required.', html)
        self.assertIn('Kept', html)
        self.assertIn('value="#dc3545" checked', html)
        self.assertFalse(Project.objects.filter(description='Kept').exists())

    def test_invalid_edit_from_the_modal_returns_the_bound_modal(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('project_update', args=[self.project.slug]), {
            'name': '',
            'description': 'Still here',
            'status': 'active',
            'color': '#198754',
        }, **AJAX)
        self.assertEqual(response.status_code, 422)
        html = response.content.decode()
        self.assertIn('data-modal-name="project_edit"', html)
        self.assertIn('This field is required.', html)
        self.assertIn('Still here', html)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'Keyed Project')


class ProjectPageModalsTest(TestCase):

    def setUp(self):
        from apps.projects.factories import ItemFactory, SectionFactory
        from apps.projects.models import ItemAttributeValue, ProjectAttribute
        self.admin = UserFactory()
        self.editor = UserFactory()
        self.viewer = UserFactory()
        self.stranger = UserFactory()
        self.project = ProjectFactory(name='Modal Project')
        ProjectMembershipFactory(project=self.project, user=self.admin, role='admin')
        ProjectMembershipFactory(project=self.project, user=self.editor, role='editor')
        ProjectMembershipFactory(project=self.project, user=self.viewer, role='viewer')
        self.section = SectionFactory(project=self.project, number='1', title='Scope')
        self.child = SectionFactory(project=self.project, number='1.1', title='Context', parent=self.section)
        self.attribute = ProjectAttribute.objects.create(project=self.project, name='Severity', field_type='dropdown', options=['Low', 'High'], is_builtin=False, order=0)
        self.item = ItemFactory(project=self.project, section=self.child, item_id='REQ-007', text='<p>Prefilled text</p>', status='approved', priority='high', created_by=self.admin, assignee=self.editor)
        ItemAttributeValue.objects.create(item=self.item, attribute=self.attribute, value='High')
        self.params = {'project': self.project.slug}

    def modal(self, name, user, **extra):
        self.client.force_login(user)
        params = dict(self.params, **extra)
        return self.client.get(reverse('modal', args=[name]), params, **AJAX)

    def test_roles_per_modal(self):
        expectations = {
            'add_item': ('editor', 403, 404),
            'edit_item': ('editor', 403, 404),
            'delete_item': ('editor', 403, 404),
            'add_link': ('editor', 403, 404),
            'manage_sections': ('editor', 403, 404),
            'collaborators': ('member', 200, 404),
            'export': ('member', 200, 404),
            'save_view': ('member', 200, 404),
        }
        for name, (level, viewer_status, stranger_status) in expectations.items():
            extra = {'item': str(self.item.public_key)} if name in ('edit_item', 'delete_item') else {}
            self.assertEqual(self.modal(name, self.editor, **extra).status_code, 200, name)
            self.assertEqual(self.modal(name, self.viewer, **extra).status_code, viewer_status, name)
            self.assertEqual(self.modal(name, self.stranger, **extra).status_code, stranger_status, name)
            self.client.force_login(self.editor)
            self.assertEqual(self.client.get(reverse('modal', args=[name]), extra, **AJAX).status_code, 404, name)

    def test_add_item_renders_sections_members_and_attribute_fields(self):
        response = self.modal('add_item', self.editor, section=str(self.child.public_key))
        html = response.content.decode()
        self.assertIn('id="addItemModal"', html)
        self.assertIn(f'<option value="{self.child.pk}" selected>1.1 Context</option>', html)
        self.assertIn(f'<option value="{self.section.pk}">1 Scope</option>', html)
        self.assertIn('id="addItemAssignee"', html)
        self.assertIn(f'data-attr-id="{self.attribute.pk}"', html)
        self.assertIn('<option value="High">High</option>', html)
        self.assertIn('id="addItemSubmit"', html)
        self.assertEqual(self.modal('add_item', self.editor, section='not-a-key').status_code, 404)

    def test_edit_item_is_prefilled(self):
        response = self.modal('edit_item', self.editor, item=str(self.item.public_key))
        html = response.content.decode()
        self.assertIn('id="editItemModal"', html)
        self.assertIn('REQ-007', html)
        self.assertIn(f'data-item-key="{self.item.public_key}"', html)
        self.assertIn('&lt;p&gt;Prefilled text&lt;/p&gt;</textarea>', html)
        self.assertIn(f'<option value="{self.child.pk}" selected>1.1 Context</option>', html)
        self.assertIn('<option value="approved" selected>', html)
        self.assertIn('<option value="high" selected>', html)
        self.assertIn(f'value="{self.editor.pk}" data-color', html)
        self.assertIn('<option value="High" selected>High</option>', html)
        self.assertNotIn('id="editItemImagePreview"', html)

    def test_delete_item_names_the_item(self):
        html = self.modal('delete_item', self.editor, item=str(self.item.public_key)).content.decode()
        self.assertIn('<strong id="deleteItemId">REQ-007</strong>', html)
        self.assertIn(f'data-item-key="{self.item.public_key}"', html)

    def test_item_of_another_project_is_not_found(self):
        other = ProjectFactory()
        from apps.projects.factories import ItemFactory, SectionFactory
        foreign = ItemFactory(project=other, section=SectionFactory(project=other), item_id='REQ-001', created_by=self.admin)
        self.assertEqual(self.modal('edit_item', self.editor, item=str(foreign.public_key)).status_code, 404)

    def test_collaborators_renders_controls_for_an_admin_and_badges_for_others(self):
        html = self.modal('collaborators', self.admin).content.decode()
        self.assertIn('id="inviteBtn"', html)
        self.assertEqual(html.count('class="form-select form-select-sm collab-role-select"'), 3)
        self.assertIn('data-current-role="editor"', html)
        self.assertIn(self.editor.email, html)
        html = self.modal('collaborators', self.viewer).content.decode()
        self.assertNotIn('id="inviteBtn"', html)
        self.assertNotIn('collab-role-select', html)
        self.assertEqual(html.count('class="badge bg-'), 3)

    def test_export_preselects_the_format_and_lists_the_attributes(self):
        html = self.modal('export', self.viewer, format='docx').content.decode()
        self.assertIn('value="docx" checked', html)
        self.assertNotIn('value="pdf" checked', html)
        self.assertIn(f'name="export_attr_ids" value="{self.attribute.pk}"', html)
        self.assertIn(f'action="{reverse("project_export", args=[self.project.slug])}"', html)
        self.assertIn('form="exportForm"', html)
        html = self.modal('export', self.viewer, format='exe').content.decode()
        self.assertIn('value="pdf" checked', html)

    def test_add_link_lists_the_link_types(self):
        html = self.modal('add_link', self.editor).content.decode()
        self.assertIn('<option value="traces-to">Traces to</option>', html)
        self.assertIn('<option value="related-to">Related to</option>', html)
        self.assertIn('id="linkTargetSearch"', html)

    def test_manage_sections_renders_the_tree_and_attribute_rows(self):
        html = self.modal('manage_sections', self.editor).content.decode()
        self.assertIn('id="manageSectionsModal"', html)
        self.assertIn(f'data-section-id="{self.section.pk}" data-section-key="{self.section.public_key}"', html)
        self.assertIn(f'data-section-id="{self.child.pk}" data-section-key="{self.child.public_key}"', html)
        self.assertIn('value="Scope"', html)
        self.assertIn('value="Context"', html)
        self.assertIn(f'data-attr-id="{self.attribute.pk}" data-attr-key="{self.attribute.public_key}"', html)
        self.assertIn('value="Severity"', html)
        self.assertIn('value="Low, High"', html)
        self.assertIn('id="mgmtSectionTemplate"', html)
        self.assertIn('id="mgmtAttributeTemplate"', html)
        self.assertIn(f'data-project="{self.project.slug}"', html)
