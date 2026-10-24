import json

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.doctemplates.factories import TemplateAttributeFactory, TemplateFactory, TemplateSectionFactory
from apps.doctemplates.models import Template
from apps.projects.tests.test_uploads import image_bytes

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


def outline(owner, **fields):
    template = TemplateFactory(
        name='Incident Review Outline', description='Review after an incident', doc_type='risk', created_by=owner,
        **fields,
    )
    summary = TemplateSectionFactory(template=template, number='1', title='Summary', description='What happened', order=0, parent=None)
    timeline = TemplateSectionFactory(template=template, number='1.1', title='Timeline', description='', order=1, parent=summary)
    TemplateSectionFactory(template=template, number='1.1.1', title='Detection', description='How it was found', order=2, parent=timeline)
    TemplateSectionFactory(template=template, number='2', title='Actions', description='Follow-up work', order=3, parent=None)
    TemplateAttributeFactory(template=template, name='Severity', field_type='dropdown', options=['Low', 'High'], order=0)
    TemplateAttributeFactory(template=template, name='Areas', field_type='multiselect', options=['Network', 'Storage'], order=1)
    TemplateAttributeFactory(template=template, name='Owner', field_type='user', options=[], order=2)
    return template


def template_json(**changes):
    data = {
        'format': 'arcspec-template',
        'version': 1,
        'name': 'Imported Outline',
        'description': '',
        'doc_type': 'custom',
        'sections': [{'title': 'Scope', 'description': '', 'children': []}],
        'attributes': [],
    }
    data.update(changes)
    return json.dumps(data).encode()


def structure(template):
    sections = [
        (s.number, s.title, s.description, s.parent.number if s.parent else None, s.order)
        for s in template.sections.select_related('parent').order_by('order')
    ]
    attributes = [(a.name, a.field_type, a.options, a.order, a.is_builtin) for a in template.attributes.order_by('order')]
    return sections, attributes


class TemplateExportTest(TestCase):

    def setUp(self):
        self.owner = UserFactory()
        self.template = outline(self.owner)

    def export(self, template):
        return self.client.get(reverse('template_export', args=[template.public_key]))

    def test_export_returns_the_template_tree_and_attributes_as_a_json_attachment(self):
        self.client.force_login(self.owner)
        response = self.export(self.template)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="incident-review-outline.json"')
        self.assertEqual(json.loads(response.content), {
            'format': 'arcspec-template',
            'version': 1,
            'name': 'Incident Review Outline',
            'description': 'Review after an incident',
            'doc_type': 'risk',
            'sections': [
                {'title': 'Summary', 'description': 'What happened', 'children': [
                    {'title': 'Timeline', 'description': '', 'children': [
                        {'title': 'Detection', 'description': 'How it was found', 'children': []},
                    ]},
                ]},
                {'title': 'Actions', 'description': 'Follow-up work', 'children': []},
            ],
            'attributes': [
                {'name': 'Severity', 'type': 'dropdown', 'options': ['Low', 'High']},
                {'name': 'Areas', 'type': 'multiselect', 'options': ['Network', 'Storage']},
                {'name': 'Owner', 'type': 'user'},
            ],
        })

    def test_a_name_that_gives_no_slug_exports_as_template_json(self):
        self.client.force_login(self.owner)
        self.template.name = 'Обзор'
        self.template.save()
        self.assertEqual(self.export(self.template)['Content-Disposition'], 'attachment; filename="template.json"')

    def test_export_links_give_the_browser_the_file_name(self):
        self.client.force_login(self.owner)
        url = reverse('template_export', args=[self.template.public_key])
        pages = (
            ('card', self.client.get(reverse('template_list'))),
            ('dialog', self.client.get(reverse('modal', args=['template_view']), {'template': self.template.public_key}, **AJAX)),
        )
        for label, response in pages:
            with self.subTest(label):
                self.assertRegex(response.content.decode(), rf'href="{url}"[^>]*download="incident-review-outline\.json"')

    def test_export_follows_who_can_see_the_template(self):
        builtin = TemplateFactory(is_builtin=True, is_global=True, created_by=None)
        public = TemplateFactory(is_global=True, created_by=self.owner)
        cases = (
            ('viewer, built-in', ViewerUserFactory(), builtin, 200),
            ('user, public of another user', UserFactory(), public, 200),
            ('user, private of another user', UserFactory(), self.template, 403),
            ('administrator, private of another user', AdminUserFactory(), self.template, 200),
        )
        for label, user, template, status in cases:
            with self.subTest(label):
                self.client.force_login(user)
                response = self.export(template)
                self.assertEqual(response.status_code, status)
                if status == 200:
                    self.assertEqual(json.loads(response.content)['name'], template.name)
                else:
                    self.assertNotIn(b'Incident Review Outline', response.content)
        self.client.logout()
        url = reverse('template_export', args=[builtin.public_key])
        self.assertRedirects(self.client.get(url), f'/?next={url}')


class TemplateImportTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.url = reverse('template_import')
        self.client.force_login(self.user)

    def import_file(self, content, name='template.json', **extra):
        return self.client.post(self.url, {'file': SimpleUploadedFile(name, content)}, **extra)

    def exported(self, template):
        self.client.force_login(template.created_by or AdminUserFactory())
        content = self.client.get(reverse('template_export', args=[template.public_key])).content
        self.client.force_login(self.user)
        return content

    def imported(self, content):
        before = set(Template.objects.values_list('pk', flat=True))
        self.import_file(content)
        return Template.objects.exclude(pk__in=before).get()

    def test_an_exported_file_imports_as_the_same_template(self):
        source = outline(UserFactory())
        imported = self.imported(self.exported(source))
        self.assertEqual(
            (imported.name, imported.description, imported.doc_type),
            ('Incident Review Outline', 'Review after an incident', 'risk'),
        )
        self.assertEqual(structure(imported), structure(source))

    def test_an_imported_template_is_private_and_owned_by_the_importer(self):
        cases = (
            ('public template of another user', outline(UserFactory(), is_global=True)),
            ('built-in template', outline(None, is_builtin=True, is_global=True)),
        )
        for label, source in cases:
            with self.subTest(label):
                imported = self.imported(self.exported(source))
                self.assertEqual((imported.created_by, imported.is_builtin, imported.is_global), (self.user, False, False))

    def test_import_returns_to_the_templates_page_with_the_template_name(self):
        response = self.import_file(template_json(name='Release Checklist'))
        self.assertRedirects(response, reverse('template_list'))
        self.assertEqual([str(m) for m in get_messages(response.wsgi_request)], ['Template "Release Checklist" imported.'])

    def test_a_refused_file_returns_the_dialog_with_the_reason_and_saves_nothing(self):
        cases = (
            ('notes.txt', template_json(), 'The file must be a .json file.'),
            ('large.json', b'{"x": "' + b'a' * (1024 * 1024) + b'"}', 'The file is larger than 1 MB.'),
            ('picture.json', image_bytes('PNG'), 'The content of the file is image/png, which does not match .json.'),
            ('broken.json', b'{"format": "arcspec-template", "version": 1,', 'The file is not valid JSON.'),
            ('constant.json', template_json().replace(b'"version": 1', b'"version": 1, "sections": [{"title": "Scope", "description": NaN}]'),
             'The file is not valid JSON.'),
            ('twice.json', template_json().replace(b'"name": "Imported Outline"', b'"name": "First", "name": "Second"'),
             'The file has the key &quot;name&quot; twice.'),
            ('nul.json', template_json(sections=[{'title': 'Sco\x00pe'}]), 'The file holds a NUL character.'),
            ('list.json', b'[{"name": "Outline"}]', 'The file is not an ArcSpec template file.'),
            ('other.json', b'{"format": "other-tool", "name": "Outline"}', 'The file is not an ArcSpec template file.'),
            ('no-version.json', template_json(version=True), 'The file is not an ArcSpec template file.'),
            ('newer.json', template_json(version=2), 'Version 2 of the template file format is not supported.'),
            ('owner.json', template_json(owner='someone'),
             'A template file must have a name and a doc_type, and can have a description, sections and attributes.'),
            ('sections.json', template_json(sections={'title': 'Scope'}),
             'A template file must have a name and a doc_type, and can have a description, sections and attributes.'),
            ('unnamed.json', template_json(name='  '), 'The template in the file has no name.'),
            ('long-name.json', template_json(name='N' * 151), 'The template name is longer than 150 characters.'),
            ('doc-type.json', template_json(doc_type='memo'),
             'The doc_type memo is not one of: requirements, architecture, testcases, risk, custom.'),
            ('section.json', template_json(sections=[{'title': 'Scope', 'children': [{'titel': 'Goals'}]}]),
             'Section 1.1 must be an object with a title, and can have a description and children.'),
            ('section-field.json', template_json(sections=[{'title': 'Scope', 'number': '1'}]),
             'Section 1 must be an object with a title, and can have a description and children.'),
            ('long-title.json', template_json(sections=[{'title': 'T' * 201}]),
             'The title of section 1 is longer than 200 characters.'),
            ('attribute.json', template_json(attributes=[{'name': 'Level'}]),
             'Attribute 1 must be an object with a name and a type, and can have options.'),
            ('attribute-field.json', template_json(attributes=[{'name': 'Level', 'type': 'text', 'required': True}]),
             'Attribute 1 must be an object with a name and a type, and can have options.'),
            ('options.json', template_json(attributes=[{'name': 'Level', 'type': 'dropdown', 'options': 'Low'}]),
             'Attribute 1 must be an object with a name and a type, and can have options.'),
            ('type.json', template_json(attributes=[{'name': 'Level', 'type': 'colour'}]),
             'Attribute Level has an unknown type: colour.'),
            ('long-attribute.json', template_json(attributes=[{'name': 'A' * 101, 'type': 'text'}]),
             'The name of attribute 1 is longer than 100 characters.'),
        )
        count = Template.objects.count()
        for name, content, message in cases:
            with self.subTest(name):
                response = self.import_file(content, name, **AJAX)
                self.assertEqual(response.status_code, 422)
                html = response.content.decode()
                self.assertIn('data-modal-name="template_import"', html)
                self.assertIn(f'data-import-error>{message}</div>', html)
                self.assertEqual(Template.objects.count(), count)

    def test_a_viewer_cannot_import(self):
        self.client.force_login(ViewerUserFactory())
        count = Template.objects.count()
        response = self.import_file(template_json())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Template.objects.count(), count)
