from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.factories import UserFactory
from apps.mcp import identifiers, services
from apps.mcp.errors import ToolRefusal, refusing
from apps.notifications.models import AuditLog
from apps.projects.factories import (
    CommentFactory,
    ItemAttributeValueFactory,
    ItemFactory,
    ItemTagFactory,
    PresetTagFactory,
    ProjectAttributeFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TagFactory,
    TraceabilityLinkFactory,
)
from apps.projects.models import Item, Project, ProjectMembership, ProjectVersion
from apps.projects.permissions import ProjectNotArchived


def key(user):
    return str(user.public_key)


class ProjectToolsTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(slug='booking')
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Scope')
        self.item = ItemFactory(project=self.project, section=self.section, item_id='REQ-001', created_by=self.user)

    def test_each_project_tool_refuses_a_non_member_with_not_found(self):
        outsider = key(UserFactory())
        calls = {
            'get_project': lambda: services.get_project(outsider, 'booking'),
            'list_sections': lambda: services.list_sections(outsider, 'booking'),
            'list_items': lambda: services.list_items(outsider, 'booking'),
            'get_item': lambda: services.get_item(outsider, 'booking', 'REQ-001'),
            'list_tags': lambda: services.list_tags(outsider, 'booking'),
            'list_attributes': lambda: services.list_attributes(outsider, 'booking'),
            'list_versions': lambda: services.list_versions(outsider, 'booking'),
            'list_audit_log': lambda: services.list_audit_log(outsider, 'booking'),
        }
        for name, call in calls.items():
            with self.subTest(tool=name):
                with self.assertRaises(ToolRefusal) as caught:
                    call()
                self.assertEqual(str(caught.exception), 'Not found: project booking.')

    def test_the_assignee_filter_returns_only_that_users_items(self):
        other = UserFactory()
        ProjectMembershipFactory(project=self.project, user=other, role='viewer')
        Item.objects.filter(pk=self.item.pk).update(assignee=self.user)
        ItemFactory(project=self.project, section=self.section, item_id='REQ-002', assignee=other)
        ItemFactory(project=self.project, section=self.section, item_id='REQ-003', assignee=self.user)
        result = services.list_items(key(self.user), 'booking', assignee=other.email)
        self.assertEqual([row['item_id'] for row in result['items']], ['REQ-002'])
        self.assertEqual(result['items'][0]['assignee'], {'name': str(other), 'email': other.email})

    def test_a_link_into_a_project_without_a_role_carries_the_project_name_and_item_id_only(self):
        twin = ItemFactory(project=self.project, section=self.section, item_id='REQ-002')
        foreign = ProjectFactory(name='Foreign Project', slug='foreign')
        far = ItemFactory(project=foreign, section=SectionFactory(project=foreign), item_id='REQ-009')
        own = TraceabilityLinkFactory(source_item=self.item, target_item=twin, link_type='related-to')
        out = TraceabilityLinkFactory(source_item=self.item, target_item=far, link_type='traces-to')
        back = TraceabilityLinkFactory(source_item=far, target_item=self.item, link_type='derived-from')
        result = services.get_item(key(self.user), 'booking', 'REQ-001')
        self.assertEqual(result['outgoing_links'], [
            {
                'public_key': str(own.public_key), 'type': 'related-to', 'item_id': 'REQ-002',
                'project_name': self.project.name, 'project_slug': 'booking', 'item_key': str(twin.public_key),
            },
            {
                'public_key': str(out.public_key), 'type': 'traces-to', 'item_id': 'REQ-009',
                'project_name': 'Foreign Project', 'project_slug': None, 'item_key': None,
            },
        ])
        self.assertEqual(result['incoming_links'], [{
            'public_key': str(back.public_key), 'type': 'derived-from', 'item_id': 'REQ-009',
            'project_name': 'Foreign Project', 'project_slug': None, 'item_key': None,
        }])

    def test_a_user_type_attribute_value_is_returned_as_the_email(self):
        attribute = ProjectAttributeFactory(project=self.project, name='Owner', field_type='user')
        ItemAttributeValueFactory(item=self.item, attribute=attribute, value=str(self.user.pk))
        detail = services.get_item(key(self.user), 'booking', 'REQ-001')
        listed = services.list_items(key(self.user), 'booking')
        self.assertEqual(detail['attributes'], [{'name': 'Owner', 'type': 'user', 'value': self.user.email}])
        self.assertEqual(listed['items'][0]['attributes'], [{'name': 'Owner', 'value': self.user.email}])

    def test_a_section_by_number_and_by_key_resolve_to_the_same_section(self):
        child = SectionFactory(project=self.project, parent=self.section, number='1.1', title='Users')
        self.assertEqual(identifiers.section(self.project, '1.1'), child)
        self.assertEqual(identifiers.section(self.project, str(child.public_key)), child)

    def test_a_tag_name_matching_a_preset_and_a_project_tag_is_refused_naming_both_keys(self):
        preset = PresetTagFactory(name='Twice')
        own = TagFactory(name='Twice', project=self.project)
        with self.assertRaises(ToolRefusal) as caught:
            identifiers.tag(self.project, 'Twice')
        self.assertEqual(
            str(caught.exception),
            f'Tag Twice names more than one tag; give a key: {preset.public_key}, {own.public_key}.',
        )

    def test_the_error_mapping_turns_each_exception_into_its_text(self):
        cases = (
            ('not found', Http404(), 'project booking', 'Not found: project booking.'),
            ('role', PermissionDenied(), '', 'Your role in this project does not allow this.'),
            ('archived', PermissionDenied(ProjectNotArchived.message), '', 'This project is archived. Restore it to make changes.'),
            ('invalid', ValidationError({'offset': ['offset must be a whole number of 0 or more.']}), '', 'offset: offset must be a whole number of 0 or more.'),
        )
        for case, exc, what, text in cases:
            with self.subTest(case=case):
                with self.assertRaises(ToolRefusal) as caught:
                    with refusing(what):
                        raise exc
                self.assertEqual(str(caught.exception), text)


class QueryCountTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(slug='booking')
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Scope')
        self.attribute = ProjectAttributeFactory(project=self.project, name='Owner', field_type='user')
        self.tag = TagFactory(name='Core', project=self.project)
        self.counter = 0

    def count(self, call):
        with CaptureQueriesContext(connection) as context:
            result = call()
        return len(context), result

    def add_projects(self, n):
        for _ in range(n):
            extra = ProjectFactory()
            ProjectMembershipFactory(project=extra, user=self.user, role='viewer')
            ProjectMembershipFactory(project=extra, user=UserFactory(), role='editor')

    def add_sections(self, n):
        for _ in range(n):
            parent = SectionFactory(project=self.project)
            SectionFactory(project=self.project, parent=parent)
            ItemFactory(project=self.project, section=parent)

    def add_items(self, n):
        for _ in range(n):
            self.counter += 1
            item = ItemFactory(
                project=self.project, section=self.section, item_id=f'REQ-{self.counter:03d}', assignee=UserFactory(),
            )
            ItemTagFactory(item=item, tag=self.tag)
            ItemAttributeValueFactory(item=item, attribute=self.attribute, value=str(UserFactory().pk))

    def relate(self, item, n):
        for _ in range(n):
            self.counter += 1
            other = ItemFactory(project=self.project, section=self.section, item_id=f'REQ-{self.counter:03d}')
            foreign = ProjectFactory()
            far = ItemFactory(project=foreign, section=SectionFactory(project=foreign))
            TraceabilityLinkFactory(source_item=item, target_item=other, link_type='related-to')
            TraceabilityLinkFactory(source_item=far, target_item=item, link_type='traces-to')
            CommentFactory(item=item, author=UserFactory())
            ItemTagFactory(item=item, tag=TagFactory(project=self.project))

    def test_list_projects_runs_a_constant_number_of_queries(self):
        self.add_projects(1)
        few, small = self.count(lambda: services.list_projects(key(self.user)))
        self.add_projects(4)
        many, large = self.count(lambda: services.list_projects(key(self.user)))
        self.assertEqual((many, len(small['projects']), len(large['projects'])), (few, 2, 6))

    def test_list_sections_runs_a_constant_number_of_queries(self):
        self.add_sections(1)
        few, small = self.count(lambda: services.list_sections(key(self.user), 'booking'))
        self.add_sections(4)
        many, large = self.count(lambda: services.list_sections(key(self.user), 'booking'))
        self.assertEqual((many, len(small['sections']), len(large['sections'])), (few, 2, 6))

    def test_list_items_runs_a_constant_number_of_queries(self):
        self.add_items(1)
        few, small = self.count(lambda: services.list_items(key(self.user), 'booking'))
        self.add_items(4)
        many, large = self.count(lambda: services.list_items(key(self.user), 'booking'))
        self.assertEqual((many, len(small['items']), len(large['items'])), (few, 1, 5))

    def test_get_item_runs_a_constant_number_of_queries(self):
        item = ItemFactory(project=self.project, section=self.section, item_id='REQ-100')
        ItemAttributeValueFactory(item=item, attribute=self.attribute, value=str(self.user.pk))
        self.relate(item, 1)
        few, small = self.count(lambda: services.get_item(key(self.user), 'booking', 'REQ-100'))
        self.relate(item, 4)
        many, large = self.count(lambda: services.get_item(key(self.user), 'booking', 'REQ-100'))
        self.assertEqual(many, few)
        self.assertEqual(
            (len(small['comments']), len(large['comments']), len(large['outgoing_links']), len(large['incoming_links']), len(large['tags'])),
            (1, 5, 5, 5, 5),
        )


class PaginationTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(slug='booking')
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)

    def make_projects(self, n):
        existing = Project.objects.for_user(self.user).count()
        projects = Project.objects.bulk_create([
            Project(name=f'Paged {k}', slug=f'paged-{k}', template=self.project.template, created_by=self.user)
            for k in range(n - existing)
        ])
        ProjectMembership.objects.bulk_create([
            ProjectMembership(project=project, user=self.user, role='viewer') for project in projects
        ])

    def make_items(self, n):
        Item.objects.bulk_create([
            Item(project=self.project, section=self.section, item_id=f'REQ-{k:03d}', text='<p>t</p>', created_by=self.user, order=k)
            for k in range(n)
        ])

    def make_versions(self, n):
        ProjectVersion.objects.bulk_create([
            ProjectVersion(project=self.project, version_number=str(k), changed_by=self.user) for k in range(n)
        ])

    def make_entries(self, n):
        existing = AuditLog.objects.filter(project=self.project).count()
        AuditLog.objects.bulk_create([
            AuditLog(project=self.project, user=self.user, action='created', target_type='Item', target_id=f'REQ-{k:03d}')
            for k in range(n - existing)
        ])

    def tools(self):
        user = key(self.user)
        return (
            ('list_projects', self.make_projects, lambda **kw: services.list_projects(user, **kw), 'projects', 100),
            ('list_items', self.make_items, lambda **kw: services.list_items(user, 'booking', **kw), 'items', 100),
            ('list_versions', self.make_versions, lambda **kw: services.list_versions(user, 'booking', **kw), 'versions', 50),
            ('list_audit_log', self.make_entries, lambda **kw: services.list_audit_log(user, 'booking', **kw), 'entries', 100),
        )

    def test_offset_limit_and_has_more_across_a_page_boundary(self):
        for name, make, call, field, maximum in self.tools():
            with self.subTest(tool=name):
                make(3)
                first = call(limit=2)
                second = call(offset=2, limit=2)
                self.assertEqual((len(first[field]), first['has_more']), (2, True))
                self.assertEqual((len(second[field]), second['has_more']), (1, False))

    def test_a_limit_above_the_maximum_is_capped(self):
        for name, make, call, field, maximum in self.tools():
            with self.subTest(tool=name):
                make(maximum + 1)
                result = call(limit=maximum + 1)
                self.assertEqual((len(result[field]), result['has_more']), (maximum, True))
