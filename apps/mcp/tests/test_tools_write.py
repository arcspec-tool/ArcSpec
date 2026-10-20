from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core import mail
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken as GrantedToken
from mcp_types import CallToolRequestParams

from apps.accounts.factories import UserFactory
from apps.mcp import services
from apps.mcp.errors import ToolRefusal
from apps.mcp.server import build_server, on_call_tool
from apps.notifications.models import AuditLog, Notification
from apps.projects import writes
from apps.projects.factories import (
    ItemAttributeValueFactory,
    ItemFactory,
    ItemTagFactory,
    ProjectAttributeFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TagFactory,
)
from apps.projects.models import Comment, Item, ItemTag, Project, ProjectVersion, TraceabilityLink


def key(user):
    return str(user.public_key)


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
        arguments = {
            'create_item': {'project': 'booking', 'section': '1', 'text': 'New'},
            'create_items': {'project': 'booking', 'items': [{'section': '1', 'text': 'New'}]},
            'update_item': {'project': 'booking', 'item': 'REQ-001', 'status': 'approved'},
            'set_item_tags': {'project': 'booking', 'item': 'REQ-001', 'remove': []},
            'add_comment': {'project': 'booking', 'item': 'REQ-001', 'text': 'Note'},
            'add_link': {'project': 'booking', 'item': 'REQ-001', 'target_item': 'REQ-001', 'type': 'related-to'},
        }
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
        self.assertEqual(self.last_row(), last)

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
