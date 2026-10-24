import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.doctemplates.factories import (
    TemplateAttributeFactory,
    TemplateFactory,
    TemplateSectionFactory,
)
from apps.doctemplates.models import Template


class TemplateListViewTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('template_list')

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/?next={self.url}')

    def test_context_separates_builtin_and_custom(self):
        builtin = TemplateFactory(is_builtin=True, name='Shared Outline')
        custom = TemplateFactory(is_builtin=False, name='My Template', created_by=self.user)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertIn(builtin, response.context['builtin_templates'])
        self.assertIn(custom, response.context['custom_templates'])
        self.assertNotIn(custom, response.context['builtin_templates'])
        self.assertNotIn(builtin, response.context['custom_templates'])

    def test_a_creator_less_custom_template_shows_as_retired_to_admins_only(self):
        retired = TemplateFactory(name='Retired Outline', is_builtin=False, is_global=False, created_by=None)
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(retired, response.context['custom_templates'])
        self.assertContains(response, 'Retired built-in template')
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(retired, response.context['custom_templates'])

    def test_search_filter(self):
        wanted = TemplateFactory(is_builtin=True, name='Zephyr Requirements')
        TemplateFactory(is_builtin=False, name='Test Cases', created_by=self.user)
        self.client.force_login(self.user)
        response = self.client.get(self.url, {'q': 'Zephyr'})
        self.assertEqual(list(response.context['builtin_templates']), [wanted])
        self.assertEqual(len(response.context['custom_templates']), 0)

    def test_usage_count_annotation(self):
        from apps.projects.factories import ProjectFactory
        tmpl = TemplateFactory(is_builtin=True)
        ProjectFactory(template=tmpl)
        ProjectFactory(template=tmpl)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        builtin = next(t for t in response.context['builtin_templates'] if t.pk == tmpl.pk)
        self.assertEqual(builtin.usage_count, 2)

    def test_section_and_attribute_counts(self):
        tmpl = TemplateFactory(is_builtin=True)
        TemplateSectionFactory(template=tmpl, number='1', title='Introduction', parent=None)
        TemplateSectionFactory(template=tmpl, number='2', title='Requirements', parent=None)
        TemplateAttributeFactory(template=tmpl)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        builtin = response.context['builtin_templates'][0]
        self.assertEqual((builtin.section_total, builtin.attribute_total, builtin.usage_count), (2, 1, 0))
        self.assertContains(response, '<span>Requirements</span> &middot; <span>2 sections</span> &middot; <span>1 attribute</span></p>')

    def test_duplicate_and_delete_forms_ask_for_confirmation(self):
        builtin = TemplateFactory(is_builtin=True, name='Built In')
        custom = TemplateFactory(is_builtin=False, name='Mine', created_by=self.user)
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count('id="confirmModal"'), 0)
        self.assertEqual(html.count('id="confirmTarget"'), 1)
        forms = re.findall(r'<form\b[^>]*>', html)
        self.assertNotIn('id="templateEditorModal"', html)
        self.assertNotIn('id="viewTemplateModal"', html)
        self.assertNotIn('data-bs-toggle="modal"', html)
        self.assertEqual(html.count('data-modal-open="template_editor"'), 2)
        cards = Template.objects.count()
        self.assertEqual(html.count('title="View structure"'), cards)
        self.assertEqual(html.count('data-modal-open="template_view"'), 2 * cards)
        expected = (
            (builtin, 'template_duplicate', 'Duplicate'),
            (custom, 'template_duplicate', 'Duplicate'),
            (custom, 'template_delete', 'Delete'),
        )
        for tmpl, route, verb in expected:
            action = reverse(route, args=[tmpl.public_key])
            matching = [form for form in forms if f'action="{action}"' in form]
            self.assertTrue(matching, action)
            for form in matching:
                self.assertIn(f'&quot;{tmpl.name}', form)
                self.assertIn('data-confirm="', form)
                self.assertIn(f'data-confirm-title="{verb} Template"', form)
                self.assertIn(f'data-confirm-button="{verb}"', form)


class TemplateListPageTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('template_list')
        self.client.force_login(self.user)

    def test_delete_is_offered_only_while_no_project_uses_the_template(self):
        from apps.projects.factories import ProjectFactory
        used = TemplateFactory(name='Used', created_by=self.user)
        ProjectFactory(template=used)
        unused = TemplateFactory(name='Unused', created_by=self.user)
        html = self.client.get(self.url).content.decode()
        self.assertNotIn(f'action="{reverse("template_delete", args=[used.public_key])}"', html)
        self.assertIn(f'action="{reverse("template_delete", args=[unused.public_key])}"', html)
        self.assertIn('Delete is unavailable: used by 1 project', html)

    def test_type_filter_counts_and_fallback(self):
        TemplateFactory(is_builtin=True, doc_type='risk')
        TemplateFactory(is_builtin=True, doc_type='requirements')
        response = self.client.get(self.url, {'type': 'nonsense'})
        self.assertEqual(response.context['selected_type'], '')
        filters = {value: count for value, label, count in response.context['type_filters']}
        self.assertEqual(filters[''], Template.objects.count())
        self.assertEqual(filters['risk'], Template.objects.filter(doc_type='risk').count())
        response = self.client.get(self.url, {'type': 'risk'})
        self.assertEqual(len(response.context['builtin_templates']), Template.objects.filter(doc_type='risk', is_builtin=True).count())
        self.assertTrue(all(t.doc_type == 'risk' for t in response.context['builtin_templates']))
        self.assertContains(response, 'aria-current="page">Risk Analysis')

    def test_viewer_gets_no_create_import_or_duplicate(self):
        TemplateFactory(is_builtin=True)
        self.assertIn('data-modal-open="template_import"', self.client.get(self.url).content.decode())
        self.client.force_login(ViewerUserFactory())
        html = self.client.get(self.url).content.decode()
        self.assertNotIn('data-modal-open="template_editor"', html)
        self.assertNotIn('data-modal-open="template_import"', html)
        self.assertNotIn('data-confirm-title="Duplicate Template"', html)

    def test_queries_do_not_grow_with_the_number_of_templates(self):
        TemplateFactory(name='One', created_by=self.user)
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for i in range(5):
            tmpl = TemplateFactory(name=f'More {i}', is_global=True)
            TemplateSectionFactory(template=tmpl)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few), len(many))


class TemplateCreateViewTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('template_create')

    def test_login_required(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, f'/?next={self.url}')

    def test_viewer_cannot_create(self):
        viewer = ViewerUserFactory()
        self.client.force_login(viewer)
        response = self.client.post(self.url, {
            'name': 'New Template',
            'doc_type': 'requirements',
        })
        self.assertEqual(response.status_code, 403)

    def test_create_template_success(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': 'New Template',
            'description': 'A test template',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '2',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'sections-0-title': 'Introduction',
            'sections-0-number': '1',
            'sections-0-order': '0',
            'sections-0-parent': '',
            'sections-1-title': 'Requirements',
            'sections-1-number': '2',
            'sections-1-order': '1',
            'sections-1-parent': '',
        })
        self.assertRedirects(response, reverse('template_list'))
        tmpl = Template.objects.get(name='New Template')
        self.assertEqual(tmpl.created_by, self.user)
        self.assertFalse(tmpl.is_builtin)
        self.assertEqual(tmpl.sections.count(), 2)

    def test_create_template_with_section_descriptions(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': 'Described Template',
            'description': 'A template with section descriptions',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '1',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'sections-0-title': 'Introduction',
            'sections-0-number': '1',
            'sections-0-order': '0',
            'sections-0-parent': '',
            'sections-0-description': 'Overview of the document purpose',
        })
        self.assertRedirects(response, reverse('template_list'))
        from apps.doctemplates.models import TemplateSection
        section = TemplateSection.objects.get(
            template__name='Described Template', title='Introduction'
        )
        self.assertEqual(section.description, 'Overview of the document purpose')

    def test_create_without_name_fails(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': '',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '0',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
        })
        self.assertRedirects(response, reverse('template_list'))
        self.assertFalse(Template.objects.filter(name='').exists())

    def test_duplicate_attribute_names_are_refused_and_nothing_is_saved(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': 'Duplicate Attributes',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '1',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'sections-0-title': 'Introduction',
            'sections-0-number': '1',
            'sections-0-order': '0',
            'sections-0-parent_ref': '',
            'sections-0-ref': 'ref-0',
            'attr_name[]': ['Severity', 'Severity'],
            'attr_type[]': ['text', 'text'],
            'attr_options[]': ['', ''],
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 422)
        self.assertIn('Attribute names must be unique: Severity.', response.content.decode())
        self.assertFalse(Template.objects.filter(name='Duplicate Attributes').exists())

    def test_create_without_name_from_the_modal_returns_the_bound_modal(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': '',
            'description': 'Kept on error',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '2',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'sections-0-title': 'Introduction',
            'sections-0-number': '1',
            'sections-0-order': '0',
            'sections-0-parent_ref': '',
            'sections-0-ref': 'ref-0',
            'sections-1-title': 'Purpose',
            'sections-1-number': '1.1',
            'sections-1-order': '1',
            'sections-1-parent_ref': 'ref-0',
            'sections-1-ref': 'ref-1',
            'attr_name[]': ['Severity'],
            'attr_type[]': ['dropdown'],
            'attr_options[]': ['Low, High'],
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 422)
        html = response.content.decode()
        self.assertIn('data-modal-name="template_editor"', html)
        self.assertIn('This field is required.', html)
        self.assertIn('Kept on error', html)
        self.assertIn('value="Introduction"', html)
        self.assertIn('value="Purpose"', html)
        self.assertIn('value="Severity"', html)
        self.assertIn('value="Low, High"', html)
        self.assertFalse(Template.objects.filter(description='Kept on error').exists())


class TemplateUpdateViewTest(TestCase):

    def setUp(self):
        self.owner = UserFactory()
        self.tmpl = TemplateFactory(created_by=self.owner, name='Original')
        self.url = reverse('template_edit', kwargs={'public_key': self.tmpl.public_key})

    def test_owner_can_update(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, {
            'name': 'Updated Name',
            'description': 'Updated desc',
            'doc_type': 'testcases',
            'sections-TOTAL_FORMS': '0',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
        })
        self.assertRedirects(response, reverse('template_list'))
        self.tmpl.refresh_from_db()
        self.assertEqual(self.tmpl.name, 'Updated Name')
        self.assertEqual(self.tmpl.doc_type, 'testcases')

    def test_admin_can_update_others_template(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.post(self.url, {
            'name': 'Admin Updated',
            'description': '',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '0',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
        })
        self.assertRedirects(response, reverse('template_list'))
        self.tmpl.refresh_from_db()
        self.assertEqual(self.tmpl.name, 'Admin Updated')

    def test_non_owner_non_admin_cannot_update(self):
        other = UserFactory()
        self.client.force_login(other)
        response = self.client.post(self.url, {'name': 'Hacked'})
        self.assertEqual(response.status_code, 403)

    def test_builtin_template_cannot_be_updated(self):
        builtin = TemplateFactory(is_builtin=True)
        url = reverse('template_edit', kwargs={'public_key': builtin.public_key})
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.post(url, {'name': 'Hacked'})
        self.assertEqual(response.status_code, 403)


class TemplateDeleteViewTest(TestCase):

    def setUp(self):
        self.owner = UserFactory()
        self.tmpl = TemplateFactory(created_by=self.owner)
        self.url = reverse('template_delete', kwargs={'public_key': self.tmpl.public_key})

    def test_owner_can_delete(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('template_list'))
        self.assertFalse(Template.objects.filter(pk=self.tmpl.pk).exists())

    def test_admin_can_delete_others_template(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('template_list'))
        self.assertFalse(Template.objects.filter(pk=self.tmpl.pk).exists())

    def test_non_owner_non_admin_cannot_delete(self):
        other = UserFactory()
        self.client.force_login(other)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)

    def test_builtin_cannot_be_deleted(self):
        builtin = TemplateFactory(is_builtin=True)
        url = reverse('template_delete', kwargs={'public_key': builtin.public_key})
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_template_with_projects_cannot_be_deleted(self):
        from apps.projects.factories import ProjectFactory
        ProjectFactory(template=self.tmpl)
        self.client.force_login(self.owner)
        response = self.client.post(self.url)
        self.assertTrue(Template.objects.filter(pk=self.tmpl.pk).exists())


class TemplateDuplicateViewTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.tmpl = TemplateFactory(
            is_builtin=True, name='Shared Outline', description='Original desc'
        )
        TemplateSectionFactory(template=self.tmpl, number='1', title='Intro')
        TemplateSectionFactory(template=self.tmpl, number='2', title='Scope')
        self.url = reverse('template_duplicate', kwargs={'public_key': self.tmpl.public_key})

    def test_duplicate_creates_copy(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('template_list'))
        copy = Template.objects.filter(name='Shared Outline (Copy)').first()
        self.assertIsNotNone(copy)
        self.assertFalse(copy.is_builtin)
        self.assertEqual(copy.created_by, self.user)
        self.assertEqual(copy.sections.count(), 2)
        self.assertEqual(copy.doc_type, self.tmpl.doc_type)

    def test_viewer_cannot_duplicate(self):
        viewer = ViewerUserFactory()
        self.client.force_login(viewer)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)

    def test_duplicate_copies_section_descriptions(self):
        from apps.doctemplates.models import TemplateSection
        TemplateSection.objects.filter(template=self.tmpl, title='Intro').update(
            description='Introduction overview'
        )
        self.client.force_login(self.user)
        self.client.post(self.url)
        copy = Template.objects.get(name='Shared Outline (Copy)')
        copied_section = copy.sections.get(title='Intro')
        self.assertEqual(copied_section.description, 'Introduction overview')

    def test_duplicate_custom_template(self):
        custom = TemplateFactory(is_builtin=False, name='Custom', created_by=self.user)
        TemplateSectionFactory(template=custom, number='1', title='Section 1')
        url = reverse('template_duplicate', kwargs={'public_key': custom.public_key})
        self.client.force_login(self.user)
        self.client.post(url)
        self.assertTrue(Template.objects.filter(name='Custom (Copy)').exists())

    def test_cannot_duplicate_private_template_of_other_user(self):
        owner = UserFactory()
        private_tmpl = TemplateFactory(
            is_builtin=False, is_global=False, name='Private',
            created_by=owner,
        )
        url = reverse('template_duplicate', kwargs={'public_key': private_tmpl.public_key})
        self.client.force_login(self.user)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Template.objects.filter(name='Private (Copy)').exists())

    def test_can_duplicate_global_template_of_other_user(self):
        owner = UserFactory()
        global_tmpl = TemplateFactory(
            is_builtin=False, is_global=True, name='Shared',
            created_by=owner,
        )
        url = reverse('template_duplicate', kwargs={'public_key': global_tmpl.public_key})
        self.client.force_login(self.user)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('template_list'))
        self.assertTrue(Template.objects.filter(name='Shared (Copy)').exists())

    def test_admin_can_duplicate_private_template_of_other_user(self):
        admin = AdminUserFactory()
        owner = UserFactory()
        private_tmpl = TemplateFactory(
            is_builtin=False, is_global=False, name='Private',
            created_by=owner,
        )
        url = reverse('template_duplicate', kwargs={'public_key': private_tmpl.public_key})
        self.client.force_login(admin)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('template_list'))
        self.assertTrue(Template.objects.filter(name='Private (Copy)').exists())

    def test_owner_can_duplicate_own_private_template(self):
        private_tmpl = TemplateFactory(
            is_builtin=False, is_global=False, name='MyPrivate',
            created_by=self.user,
        )
        url = reverse('template_duplicate', kwargs={'public_key': private_tmpl.public_key})
        self.client.force_login(self.user)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('template_list'))
        self.assertTrue(Template.objects.filter(name='MyPrivate (Copy)').exists())


class TemplateCreateWithAttributesTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('template_create')

    def test_create_template_with_dropdown_attribute(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': 'Attr Template',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '0',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'attr_name[]': ['Risk Level'],
            'attr_type[]': ['dropdown'],
            'attr_options[]': ['Low, Medium, High'],
        })
        self.assertRedirects(response, reverse('template_list'))
        from apps.doctemplates.models import TemplateAttribute
        attr = TemplateAttribute.objects.get(template__name='Attr Template')
        self.assertEqual(attr.field_type, 'dropdown')
        self.assertEqual(attr.options, ['Low', 'Medium', 'High'])

    def test_create_template_with_multiselect_attribute(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'name': 'Multi Template',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '0',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'attr_name[]': ['Environments'],
            'attr_type[]': ['multiselect'],
            'attr_options[]': ['Dev, Staging, Prod'],
        })
        self.assertRedirects(response, reverse('template_list'))
        from apps.doctemplates.models import TemplateAttribute
        attr = TemplateAttribute.objects.get(template__name='Multi Template')
        self.assertEqual(attr.field_type, 'multiselect')
        self.assertEqual(attr.options, ['Dev', 'Staging', 'Prod'])

    def test_text_attribute_ignores_options(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {
            'name': 'Text Template',
            'doc_type': 'requirements',
            'sections-TOTAL_FORMS': '0',
            'sections-INITIAL_FORMS': '0',
            'sections-MIN_NUM_FORMS': '0',
            'sections-MAX_NUM_FORMS': '1000',
            'attr_name[]': ['Notes'],
            'attr_type[]': ['text'],
            'attr_options[]': [''],
        })
        from apps.doctemplates.models import TemplateAttribute
        attr = TemplateAttribute.objects.get(template__name='Text Template')
        self.assertEqual(attr.options, [])


class TemplateDuplicateAttributesTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.tmpl = TemplateFactory(is_builtin=True, name='Original')
        from apps.doctemplates.factories import TemplateAttributeFactory
        TemplateAttributeFactory(
            template=self.tmpl, name='Risk', field_type='dropdown',
            options=['Low', 'High']
        )
        self.url = reverse('template_duplicate', kwargs={'public_key': self.tmpl.public_key})

    def test_duplicate_copies_attributes_with_options(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        from apps.doctemplates.models import TemplateAttribute
        copy = Template.objects.get(name='Original (Copy)')
        attr = copy.attributes.first()
        self.assertEqual(attr.name, 'Risk')
        self.assertEqual(attr.field_type, 'dropdown')
        self.assertEqual(attr.options, ['Low', 'High'])
