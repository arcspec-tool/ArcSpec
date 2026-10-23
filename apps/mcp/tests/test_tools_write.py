import base64
import io
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core import mail
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken as GrantedToken
from mcp_types import CallToolRequestParams
from PIL import Image

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.doctemplates.factories import TemplateAttributeFactory, TemplateFactory, TemplateSectionFactory
from apps.doctemplates.models import Template
from apps.mcp import services
from apps.mcp.errors import ToolRefusal
from apps.mcp.server import build_server, on_call_tool
from apps.notifications.models import AuditLog, Notification
from apps.projects import writes
from apps.projects.factories import (
    AttachmentFactory,
    ItemAttributeValueFactory,
    ItemFactory,
    ItemTagFactory,
    ProjectAttributeFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TagFactory,
)
from apps.projects.models import Attachment, Comment, Item, ItemTag, Project, ProjectVersion, TraceabilityLink


def key(user):
    return str(user.public_key)


def png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='red').save(buffer, format='PNG')
    return buffer.getvalue()


def jpeg_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='red').save(buffer, format='JPEG')
    return buffer.getvalue()


def encoded(content):
    return base64.b64encode(content).decode()


def call_tool(name, arguments):
    return async_to_sync(on_call_tool)(None, CallToolRequestParams(name=name, arguments=arguments))


class WriteToolTests(TestCase):

    def setUp(self):
        self.owner = UserFactory()
        self.user = UserFactory()
        self.viewer = UserFactory()
        self.project = ProjectFactory(slug='booking', name='Booking', created_by=self.owner)
        for member, role in ((self.owner, 'admin'), (self.user, 'editor'), (self.viewer, 'viewer')):
            ProjectMembershipFactory(project=self.project, user=member, role=role)
        self.first = SectionFactory(project=self.project, number='1', title='Scope', order=0)
        self.second = SectionFactory(project=self.project, number='2', title='Rules', order=1)
        self.item = ItemFactory(project=self.project, section=self.first, item_id='REQ-001', created_by=self.owner, order=1)

    def section_order(self, section):
        return list(Item.objects.filter(section=section).order_by('order').values_list('item_id', flat=True))

    def rows_after(self, last, item_id):
        return list(
            AuditLog.objects.filter(pk__gt=last, target_type='Item', target_id=item_id)
            .order_by('pk').values_list('action', 'user', 'details')
        )

    def last_row(self):
        return AuditLog.objects.order_by('-pk').values_list('pk', flat=True).first()

    def write_calls(self):
        return {
            'create_item': lambda user: services.create_item(key(user), 'booking', section='1', text='New'),
            'create_items': lambda user: services.create_items(key(user), 'booking', items=[{'section': '1', 'text': 'New'}]),
            'update_item': lambda user: services.update_item(key(user), 'booking', 'REQ-001', status='approved'),
            'set_item_tags': lambda user: services.set_item_tags(key(user), 'booking', 'REQ-001', remove=[]),
            'add_comment': lambda user: services.add_comment(key(user), 'booking', 'REQ-001', 'Note'),
            'add_link': lambda user: services.add_link(key(user), 'booking', 'REQ-001', 'REQ-001', 'related-to'),
            'set_item_image': lambda user: services.set_item_image(key(user), 'booking', 'REQ-001', 'chart.png', encoded(png_bytes())),
            'remove_item_image': lambda user: services.remove_item_image(key(user), 'booking', 'REQ-001'),
            'add_attachment': lambda user: services.add_attachment(key(user), 'booking', 'REQ-001', 'chart.png', encoded(png_bytes())),
            'remove_attachment': lambda user: services.remove_attachment(key(user), 'booking', 'REQ-001', 'no-such-attachment'),
        }

    def test_create_item_stores_the_converted_text_with_html_headings_code_and_links_as_typed_text(self):
        cases = (
            ('raw html', '**b**\n\n<script>', '<p><strong>b</strong></p>\n<p>&lt;script&gt;</p>\n'),
            ('heading', '# Title', '<p># Title</p>\n'),
            ('code', 'Use `code` here', '<p>Use `code` here</p>\n'),
            ('link', '[a](https://x.example)', '<p>[a](https://x.example)</p>\n'),
        )
        for case, text, stored in cases:
            with self.subTest(case=case):
                result = services.create_item(key(self.user), 'booking', section='1', text=text)
                self.assertEqual(Item.objects.get(public_key=result['public_key']).text, stored)

    def test_a_text_that_is_empty_after_conversion_is_refused(self):
        with self.assertRaises(ToolRefusal) as caught:
            services.create_item(key(self.user), 'booking', section='1', text='   \n')
        self.assertEqual(str(caught.exception), 'text: The text is empty after conversion.')
        self.assertEqual(self.section_order(self.first), ['REQ-001'])

    def test_an_anchor_in_another_section_is_refused(self):
        ItemFactory(project=self.project, section=self.second, item_id='REQ-002', order=1)
        with self.assertRaises(ToolRefusal) as caught:
            services.create_item(key(self.user), 'booking', section='1', text='Placed', after='REQ-002')
        self.assertEqual(str(caught.exception), 'after: The item is not in the chosen section.')

    def test_create_items_writes_consecutive_items_one_version_and_one_notification_per_other_member(self):
        last = self.last_row()
        versions = list(ProjectVersion.objects.values_list('pk', flat=True))
        result = services.create_items(key(self.user), 'booking', items=[{'section': '1', 'text': f'Entry {n}'} for n in range(3)])
        ids = [row['item_id'] for row in result['items']]
        self.assertEqual(ids, ['REQ-002', 'REQ-003', 'REQ-004'])
        self.assertEqual(self.section_order(self.first), ['REQ-001', *ids])
        created = AuditLog.objects.filter(pk__gt=last, action='created').order_by('pk').values_list('target_id', 'user')
        self.assertEqual(list(created), [(item_id, self.user.pk) for item_id in ids])
        summaries = ProjectVersion.objects.exclude(pk__in=versions).values_list('change_summary', flat=True)
        self.assertEqual(list(summaries), ['Created 3 items'])
        notifications = Notification.objects.filter(type='item_created', actor=self.user).values_list('user', 'message')
        self.assertEqual(sorted(notifications), sorted([
            (self.owner.pk, '3 new items created in Booking'), (self.viewer.pk, '3 new items created in Booking'),
        ]))

    def test_create_items_keeps_the_input_order_at_each_anchor_and_writes_tags_and_attribute_values(self):
        ItemFactory(project=self.project, section=self.first, item_id='REQ-002', order=2)
        tag = TagFactory(project=self.project, name='Batch Tag')
        risk = ProjectAttributeFactory(project=self.project, name='Risk', field_type='dropdown', options=['Low', 'High'])
        last = self.last_row()
        services.create_items(key(self.user), 'booking', items=[
            {'section': '1', 'text': 'A', 'after': 'REQ-001', 'tags': ['Batch Tag']},
            {'section': '1', 'text': 'B', 'after': 'REQ-001', 'attributes': {'Risk': 'High'}},
            {'section': '1', 'text': 'C', 'before': 'REQ-001'},
        ])
        self.assertEqual(self.section_order(self.first), ['REQ-005', 'REQ-001', 'REQ-003', 'REQ-004', 'REQ-002'])
        self.assertEqual(list(ItemTag.objects.filter(tag=tag).values_list('item__item_id', flat=True)), ['REQ-003'])
        self.assertEqual(list(risk.values.values_list('item__item_id', 'value')), [('REQ-004', 'High')])
        tag_rows = AuditLog.objects.filter(pk__gt=last, action='tag_added').values_list('target_id', 'details')
        self.assertEqual(list(tag_rows), [('REQ-003', {'tags': ['Batch Tag']})])

    def test_create_items_with_an_invalid_entry_saves_nothing_and_names_the_entry(self):
        with self.assertRaises(ToolRefusal) as caught:
            services.create_items(key(self.user), 'booking', items=[
                {'section': '1', 'text': 'Kept back'}, {'section': '9', 'text': 'Unknown section'},
            ])
        self.assertEqual(str(caught.exception), 'items[1].section: Not found: section 9.')
        self.assertEqual(self.section_order(self.first), ['REQ-001'])
        self.assertEqual(Project.objects.get(pk=self.project.pk).next_item_number, 2)

    def test_arguments_the_schema_refuses_are_answered_with_the_field_and_message_and_nothing_is_saved(self):
        build_server()
        result = call_tool('create_items', {'project': 'booking', 'items': [{'section': '1', 'text': 'x'}] * 101})
        self.assertEqual(
            (result.is_error, result.content[0].text),
            (True, 'items: List should have at most 100 items after validation, not 101'),
        )
        self.assertEqual(self.section_order(self.first), ['REQ-001'])

    def test_update_item_with_one_attribute_keeps_the_other_stored_values(self):
        risk = ProjectAttributeFactory(project=self.project, name='Risk', field_type='dropdown', options=['Low', 'High'])
        source = ProjectAttributeFactory(project=self.project, name='Source', field_type='text')
        ItemAttributeValueFactory(item=self.item, attribute=risk, value='Low')
        ItemAttributeValueFactory(item=self.item, attribute=source, value='Workshop')
        services.update_item(key(self.user), 'booking', 'REQ-001', attributes={'Risk': 'High'})
        stored = self.item.attribute_values.order_by('attribute__name').values_list('attribute__name', 'value')
        self.assertEqual(list(stored), [('Risk', 'High'), ('Source', 'Workshop')])

    def test_update_item_with_a_position_only_moves_the_item_and_writes_no_audit_row(self):
        ItemFactory(project=self.project, section=self.first, item_id='REQ-002', order=2)
        last = self.last_row()
        services.update_item(key(self.user), 'booking', 'REQ-002', before='REQ-001')
        self.assertEqual((self.section_order(self.first), self.rows_after(last, 'REQ-002')), (['REQ-002', 'REQ-001'], []))

    def test_update_item_with_a_section_change_writes_one_updated_row(self):
        last = self.last_row()
        services.update_item(key(self.user), 'booking', 'REQ-001', section='2')
        self.assertEqual((self.section_order(self.second), self.rows_after(last, 'REQ-001')), (['REQ-001'], [('updated', self.user.pk, {})]))

    def test_set_item_tags_adds_and_removes_in_one_call_and_writes_one_row_per_change(self):
        old = TagFactory(project=self.project, name='Old Tag')
        new = TagFactory(project=self.project, name='New Tag')
        ItemTagFactory(item=self.item, tag=old)
        last = self.last_row()
        result = services.set_item_tags(key(self.user), 'booking', 'REQ-001', add=['New Tag'], remove=['Old Tag'])
        self.assertEqual(result, {'tags': [{'public_key': str(new.public_key), 'name': 'New Tag'}]})
        self.assertEqual(self.rows_after(last, 'REQ-001'), [
            ('tag_added', self.user.pk, {'tags': ['New Tag']}), ('tag_removed', self.user.pk, {'tags': ['Old Tag']}),
        ])

    def test_add_comment_stores_the_text_without_conversion(self):
        result = services.add_comment(key(self.user), 'booking', 'REQ-001', '**not bold** <b>kept</b>')
        self.assertEqual(Comment.objects.get(public_key=result['public_key']).text, '**not bold** <b>kept</b>')

    def test_add_link_reaches_an_item_in_a_project_where_the_user_is_a_viewer(self):
        other = ProjectFactory(slug='other')
        ProjectMembershipFactory(project=other, user=self.user, role='viewer')
        target = ItemFactory(project=other, section=SectionFactory(project=other), item_id='REQ-001')
        result = services.add_link(key(self.user), 'booking', 'REQ-001', 'REQ-001', 'traces-to', target_project='other')
        link = TraceabilityLink.objects.get(public_key=result['public_key'])
        self.assertEqual((link.source_item, link.target_item, link.created_by), (self.item, target, self.user))

    def test_add_link_into_a_project_without_a_role_answers_not_found(self):
        hidden = ProjectFactory(slug='hidden')
        ItemFactory(project=hidden, section=SectionFactory(project=hidden), item_id='REQ-001')
        with self.assertRaises(ToolRefusal) as caught:
            services.add_link(key(self.user), 'booking', 'REQ-001', 'REQ-001', 'traces-to', target_project='hidden')
        self.assertEqual((str(caught.exception), TraceabilityLink.objects.count()), ('Not found: project hidden.', 0))

    def test_a_viewer_and_a_write_on_an_archived_project_are_refused(self):
        last = self.last_row()
        for case, archived, user, text in (
            ('viewer', False, self.viewer, 'Your role in this project does not allow this.'),
            ('archived', True, self.user, 'This project is archived. Restore it to make changes.'),
        ):
            Project.objects.filter(pk=self.project.pk).update(status='archived' if archived else 'active')
            for name, call in self.write_calls().items():
                with self.subTest(case=case, tool=name):
                    with self.assertRaises(ToolRefusal) as caught:
                        call(user)
                    self.assertEqual(str(caught.exception), text)
        self.assertEqual(self.last_row(), last)

    def test_each_write_tool_refuses_a_read_only_token_and_saves_nothing(self):
        build_server()
        owned = TemplateFactory(created_by=self.user, name='Owned')
        arguments = {
            'create_item': {'project': 'booking', 'section': '1', 'text': 'New'},
            'create_items': {'project': 'booking', 'items': [{'section': '1', 'text': 'New'}]},
            'update_item': {'project': 'booking', 'item': 'REQ-001', 'status': 'approved'},
            'set_item_tags': {'project': 'booking', 'item': 'REQ-001', 'remove': []},
            'add_comment': {'project': 'booking', 'item': 'REQ-001', 'text': 'Note'},
            'add_link': {'project': 'booking', 'item': 'REQ-001', 'target_item': 'REQ-001', 'type': 'related-to'},
            'set_item_image': {'project': 'booking', 'item': 'REQ-001', 'filename': 'chart.png', 'data': encoded(png_bytes())},
            'remove_item_image': {'project': 'booking', 'item': 'REQ-001'},
            'add_attachment': {'project': 'booking', 'item': 'REQ-001', 'filename': 'chart.png', 'data': encoded(png_bytes())},
            'remove_attachment': {'project': 'booking', 'item': 'REQ-001', 'attachment': 'no-such-attachment'},
            'create_template': {'name': 'New', 'doc_type': 'custom'},
            'update_template': {'template': str(owned.public_key), 'name': 'Renamed'},
        }
        templates = list(Template.objects.values_list('pk', 'name'))
        attachments = Attachment.objects.count()
        last = self.last_row()
        token = GrantedToken(token='', client_id='', scopes=['read'], subject=key(self.user))
        reset = auth_context_var.set(AuthenticatedUser(token))
        try:
            for name, values in arguments.items():
                with self.subTest(tool=name):
                    result = call_tool(name, values)
                    self.assertEqual((result.is_error, result.content[0].text), (True, 'This connection is read only.'))
        finally:
            auth_context_var.reset(reset)
        self.assertEqual(
            (self.last_row(), list(Template.objects.values_list('pk', 'name')), Attachment.objects.count()),
            (last, templates, attachments),
        )

    def comment_four_times(self):
        with self.captureOnCommitCallbacks(execute=True):
            for n in range(4):
                services.add_comment(key(self.user), 'booking', 'REQ-001', f'Note {n}')

    def test_the_fourth_tool_notification_within_fifteen_minutes_is_created_and_sends_no_email(self):
        self.comment_four_times()
        received = Notification.objects.filter(user=self.owner, actor=self.user, type='comment')
        self.assertEqual((received.count(), [message.to for message in mail.outbox]), (4, [[self.owner.email]] * 3))

    def test_a_page_write_after_the_limit_still_sends_its_email(self):
        self.comment_four_times()
        self.client.force_login(self.user)
        url = reverse('api_comment_list', kwargs={'slug': 'booking', 'item_key': self.item.public_key})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {'text': 'From the page'}, content_type='application/json')
        self.assertEqual((response.status_code, [message.to for message in mail.outbox]), (201, [[self.owner.email]] * 4))


class ItemFileToolTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(slug='booking')
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.item = ItemFactory(project=self.project, section=SectionFactory(project=self.project), item_id='REQ-001')

    def stored(self, name):
        with default_storage.open(name) as stored_file:
            return stored_file.read()

    def test_set_item_image_stores_the_decoded_file_in_media_as_the_item_image(self):
        content = png_bytes()
        services.set_item_image(key(self.user), 'booking', 'REQ-001', 'chart.png', encoded(content))
        self.item.refresh_from_db()
        self.assertEqual(
            (self.item.image.name.startswith('items/images/'), self.item.image.name.endswith('.png'), self.stored(self.item.image.name)),
            (True, True, content),
        )

    def test_set_item_image_replaces_the_image_and_deletes_the_old_file(self):
        services.set_item_image(key(self.user), 'booking', 'REQ-001', 'first.png', encoded(png_bytes()))
        self.item.refresh_from_db()
        old_name = self.item.image.name
        services.set_item_image(key(self.user), 'booking', 'REQ-001', 'second.png', encoded(png_bytes()))
        self.item.refresh_from_db()
        self.assertEqual((default_storage.exists(old_name), default_storage.exists(self.item.image.name)), (False, True))

    def test_remove_item_image_deletes_the_image_file(self):
        self.item.image = SimpleUploadedFile('chart.png', png_bytes())
        self.item.save()
        name = self.item.image.name
        services.remove_item_image(key(self.user), 'booking', 'REQ-001')
        self.assertEqual(default_storage.exists(name), False)

    def test_remove_item_image_without_an_image_is_refused(self):
        last = AuditLog.objects.count()
        with self.assertRaises(ToolRefusal) as caught:
            services.remove_item_image(key(self.user), 'booking', 'REQ-001')
        self.assertEqual((str(caught.exception), AuditLog.objects.count()), ('Item REQ-001 has no image.', last))

    def test_add_attachment_stores_the_decoded_file_in_media_with_its_name_and_size(self):
        content = b'%PDF-1.4\n%%EOF\n'
        result = services.add_attachment(key(self.user), 'booking', 'REQ-001', 'report.pdf', encoded(content))
        attachment = Attachment.objects.get(public_key=result['public_key'])
        self.assertEqual(
            (attachment.item, attachment.filename, attachment.file_size, attachment.file.name.startswith('attachments/'),
             self.stored(attachment.file.name)),
            (self.item, 'report.pdf', len(content), True, content),
        )

    def test_remove_attachment_removes_it_and_returns_the_remaining_ones(self):
        kept = AttachmentFactory(item=self.item, uploaded_by=self.user, filename='kept.pdf')
        removed = AttachmentFactory(item=self.item, uploaded_by=self.user, filename='removed.pdf')
        result = services.remove_attachment(key(self.user), 'booking', 'REQ-001', str(removed.public_key))
        self.assertEqual(
            (result['attachments'], list(Attachment.objects.values_list('pk', flat=True))),
            ([{'public_key': str(kept.public_key), 'filename': 'kept.pdf', 'size': kept.file_size}], [kept.pk]),
        )

    def test_remove_attachment_of_another_item_answers_not_found_and_keeps_it(self):
        other = AttachmentFactory(item=ItemFactory(project=self.project, section=self.item.section, item_id='REQ-002'))
        with self.assertRaises(ToolRefusal) as caught:
            services.remove_attachment(key(self.user), 'booking', 'REQ-001', str(other.public_key))
        self.assertEqual(
            (str(caught.exception), Attachment.objects.filter(pk=other.pk).count()),
            (f'Not found: attachment {other.public_key}.', 1),
        )

    def test_file_data_that_is_not_base64_or_does_not_match_its_extension_is_refused_and_nothing_is_saved(self):
        for case, call, text in (
            ('a character outside base64', lambda: services.add_attachment(
                key(self.user), 'booking', 'REQ-001', 'report.pdf', encoded(b'%PDF-1.4\n%%EOF\n') + '!',
            ),
             'data: The data is not valid base64.'),
            ('image content of another type',
             lambda: services.set_item_image(key(self.user), 'booking', 'REQ-001', 'chart.png', encoded(jpeg_bytes())),
             'The content of the file is image/jpeg, which does not match .png.'),
            ('attachment content of another type',
             lambda: services.add_attachment(key(self.user), 'booking', 'REQ-001', 'report.pdf', encoded(b'<html>report</html>')),
             'The content of the file is text/html, which does not match .pdf.'),
        ):
            with self.subTest(case=case):
                with self.assertRaises(ToolRefusal) as caught:
                    call()
                self.assertEqual(str(caught.exception), text)
        self.item.refresh_from_db()
        self.assertEqual((bool(self.item.image), Attachment.objects.count()), (False, 0))


class TemplateToolTests(TestCase):

    def setUp(self):
        self.owner = UserFactory()

    def sections(self, template):
        return list(template.sections.order_by('order').values_list('number', 'title', 'description', 'parent__number'))

    def attributes(self, template):
        return list(template.attributes.order_by('order').values_list('name', 'field_type', 'options', 'is_builtin', 'order'))

    def names(self):
        return list(Template.objects.order_by('pk').values_list('name', flat=True))

    def test_create_template_stores_the_section_tree_numbered_by_position_and_the_attributes_in_order(self):
        build_server()
        token = GrantedToken(token='', client_id='', scopes=['read', 'write'], subject=key(self.owner))
        reset = auth_context_var.set(AuthenticatedUser(token))
        try:
            result = call_tool('create_template', {
                'name': 'Security Review', 'doc_type': 'risk',
                'sections': [
                    {'title': 'Scope', 'description': 'What is reviewed', 'children': [{'title': 'Systems'}, {'title': 'People'}]},
                    {'title': 'Findings', 'number': '9'},
                ],
                'attributes': [
                    {'name': 'Severity', 'type': 'dropdown', 'options': ['Low', 'High']},
                    {'name': 'Due', 'type': 'date'},
                ],
            })
        finally:
            auth_context_var.reset(reset)
        created = Template.objects.get(public_key=result.structured_content['public_key'])
        self.assertEqual(self.sections(created), [
            ('1', 'Scope', 'What is reviewed', None), ('1.1', 'Systems', '', '1'), ('1.2', 'People', '', '1'),
            ('2', 'Findings', '', None),
        ])
        self.assertEqual(self.attributes(created), [('Severity', 'dropdown', ['Low', 'High'], False, 0), ('Due', 'date', [], False, 1)])

    def test_create_template_makes_the_account_the_owner_of_a_template_that_is_not_built_in(self):
        result = services.create_template(key(self.owner), 'Security Review', 'risk')
        created = Template.objects.get(public_key=result['public_key'])
        self.assertEqual((created.created_by, created.is_builtin), (self.owner, False))

    def test_a_system_viewer_cannot_create_a_template(self):
        names = self.names()
        with self.assertRaises(ToolRefusal) as caught:
            services.create_template(key(ViewerUserFactory()), 'Viewer Template', 'custom')
        self.assertEqual((str(caught.exception), self.names()), ('Your system role does not allow this.', names))

    def test_template_arguments_that_break_a_rule_are_refused_and_nothing_is_saved(self):
        deep = {'title': 'Deep'}
        for level in range(10):
            deep = {'title': 'Deep', 'children': [deep]}
        names = self.names()
        for case, arguments, text in (
            ('blank name', {'name': ' '}, 'name: This field cannot be blank.'),
            ('blank section title', {'sections': [{'title': ' '}]}, 'sections: Section 1 has no title.'),
            ('tree too deep', {'sections': [deep]},
             'sections: The section tree is too deep: section number 1.1.1.1.1.1.1.1.1.1.1 is longer than 20 characters.'),
            ('blank attribute name', {'attributes': [{'name': ' ', 'type': 'text'}]}, 'attributes: An attribute has no name.'),
            ('duplicate attribute names', {'attributes': [{'name': 'Risk', 'type': 'text'}, {'name': 'Risk', 'type': 'number'}]},
             'attributes: Attribute names must be unique: Risk.'),
            ('options on a text attribute', {'attributes': [{'name': 'Owner', 'type': 'text', 'options': ['A']}]},
             'attributes: Attribute Owner is not a dropdown or multi-select and takes no options.'),
            ('dropdown without options', {'attributes': [{'name': 'Level', 'type': 'dropdown'}]},
             'attributes: Attribute Level needs at least one option.'),
            ('option with a comma', {'attributes': [{'name': 'Level', 'type': 'multiselect', 'options': ['Low, High']}]},
             'attributes: An option of attribute Level is empty or holds a comma.'),
        ):
            with self.subTest(case=case):
                with self.assertRaises(ToolRefusal) as caught:
                    services.create_template(key(self.owner), **{'name': 'Refused', 'doc_type': 'custom', **arguments})
                self.assertEqual(str(caught.exception), text)
        self.assertEqual(self.names(), names)

    def test_update_template_changes_only_the_fields_given(self):
        template = TemplateFactory(created_by=self.owner, name='Change Request', doc_type='custom')
        TemplateSectionFactory(template=template, number='1', title='Summary', order=0)
        TemplateAttributeFactory(template=template, name='Impact', order=0)
        rows = (list(template.sections.values_list('pk', flat=True)), list(template.attributes.values_list('pk', flat=True)))
        services.update_template(key(self.owner), str(template.public_key), description='Changes to a release', visible_to_all=True)
        template.refresh_from_db()
        self.assertEqual(
            (template.name, template.description, template.doc_type, template.is_global),
            ('Change Request', 'Changes to a release', 'custom', True),
        )
        self.assertEqual(
            (list(template.sections.values_list('pk', flat=True)), list(template.attributes.values_list('pk', flat=True))), rows,
        )

    def test_update_template_with_sections_replaces_the_whole_section_tree(self):
        template = TemplateFactory(created_by=self.owner)
        TemplateSectionFactory(template=template, number='1', title='Old', order=0)
        TemplateSectionFactory(template=template, number='2', title='Older', order=1)
        services.update_template(
            key(self.owner), str(template.public_key), sections=[{'title': 'Summary', 'children': [{'title': 'Reason'}]}],
        )
        self.assertEqual(self.sections(template), [('1', 'Summary', '', None), ('1.1', 'Reason', '', '1')])

    def test_update_template_with_attributes_replaces_the_custom_attributes_and_keeps_the_built_in_ones(self):
        template = TemplateFactory(created_by=self.owner)
        TemplateAttributeFactory(template=template, name='Status', is_builtin=True, order=0)
        TemplateAttributeFactory(template=template, name='Old', order=1)
        services.update_template(
            key(self.owner), str(template.public_key),
            attributes=[{'name': 'Impact', 'type': 'multiselect', 'options': ['Cost', 'Time']}],
        )
        self.assertEqual(self.attributes(template), [('Status', 'text', [], True, 0), ('Impact', 'multiselect', ['Cost', 'Time'], False, 1)])

    def test_an_administrator_changes_another_users_private_template(self):
        template = TemplateFactory(created_by=self.owner, is_global=False, name='Private')
        services.update_template(key(AdminUserFactory()), str(template.public_key), name='Renamed')
        template.refresh_from_db()
        self.assertEqual(template.name, 'Renamed')

    def test_update_template_is_refused_for_a_template_the_account_cannot_change_and_nothing_changes(self):
        builtin = TemplateFactory(is_builtin=True, created_by=None, name='Built In')
        shared = TemplateFactory(created_by=self.owner, is_global=True, name='Shared')
        private = TemplateFactory(created_by=self.owner, is_global=False, name='Private')
        other = UserFactory()
        names = self.names()
        for case, user, value, text in (
            ('built-in, as an administrator', AdminUserFactory(), str(builtin.public_key), 'A built-in template cannot be changed.'),
            ("another user's shared template", other, str(shared.public_key),
             'Only the owner of the template or an administrator can change it.'),
            ("another user's private template", other, str(private.public_key), f'Not found: template {private.public_key}.'),
            ('unknown key', other, 'no-such-template', 'Not found: template no-such-template.'),
        ):
            with self.subTest(case=case):
                with self.assertRaises(ToolRefusal) as caught:
                    services.update_template(key(user), value, name='Changed')
                self.assertEqual(str(caught.exception), text)
        self.assertEqual(self.names(), names)


class ConflictTests(TransactionTestCase):

    def test_an_integrity_error_at_commit_returns_the_conflict_text_and_saves_nothing(self):
        user = UserFactory()
        project = ProjectFactory(slug='booking')
        ProjectMembershipFactory(project=project, user=user, role='editor')
        ItemFactory(project=project, section=SectionFactory(project=project), item_id='REQ-001')
        create_comment = writes.create_comment

        def dangling(item, author, text, parent=None):
            comment = create_comment(item, author, text, parent)
            AuditLog.objects.create(project=item.project, user_id=0, action='commented', target_type='Item', target_id=item.item_id)
            return comment

        with patch.object(writes, 'create_comment', dangling), self.assertLogs('apps.mcp.errors', 'ERROR'):
            with self.assertRaises(ToolRefusal) as caught:
                services.add_comment(key(user), 'booking', 'REQ-001', 'Lost')
        self.assertEqual(str(caught.exception), 'A conflicting change was saved at the same time. Nothing was saved.')
        self.assertEqual(Comment.objects.count(), 0)
