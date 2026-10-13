from django.test import TestCase

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.doctemplates.factories import TemplateFactory
from apps.projects.factories import (
    AttachmentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TagFactory,
)
from apps.projects.models import Item, Project, Tag


class ProjectModelTest(TestCase):

    def test_generate_item_id(self):
        tmpl = TemplateFactory(doc_type='requirements')
        project = ProjectFactory(template=tmpl)
        self.assertEqual(project.generate_item_id(), 'REQ-001')

    def test_item_count(self):
        project = ProjectFactory()
        section = SectionFactory(project=project)
        self.assertEqual(project.item_count, 0)
        ItemFactory(project=project, section=section, item_id='REQ-001')
        self.assertEqual(project.item_count, 1)

    def test_collaborator_count(self):
        project = ProjectFactory()
        self.assertEqual(project.collaborator_count, 0)
        ProjectMembershipFactory(project=project)
        self.assertEqual(project.collaborator_count, 1)

    def test_get_user_role_admin_member(self):
        project = ProjectFactory()
        user = UserFactory()
        ProjectMembershipFactory(project=project, user=user, role='admin')
        self.assertEqual(project.get_user_role(user), 'admin')

    def test_get_user_role_system_admin(self):
        project = ProjectFactory()
        admin = AdminUserFactory()
        self.assertEqual(project.get_user_role(admin), 'admin')

    def test_get_user_role_non_member(self):
        project = ProjectFactory()
        user = UserFactory()
        self.assertIsNone(project.get_user_role(user))

    def test_for_user_lists_member_projects_only_not_created_ones(self):
        user = UserFactory()
        ProjectFactory(created_by=user)
        member_project = ProjectFactory()
        ProjectMembershipFactory(project=member_project, user=user)
        ProjectFactory()
        self.assertEqual(list(Project.objects.for_user(user)), [member_project])

    def test_for_user_system_admin_sees_all(self):
        admin = AdminUserFactory()
        p1 = ProjectFactory()
        p2 = ProjectFactory()
        qs = Project.objects.for_user(admin)
        self.assertIn(p1, qs)
        self.assertIn(p2, qs)

    def test_get_absolute_url(self):
        project = ProjectFactory(slug='my-project')
        self.assertEqual(project.get_absolute_url(), '/projects/my-project/')


class SectionModelTest(TestCase):

    def test_item_count(self):
        section = SectionFactory()
        self.assertEqual(section.item_count, 0)
        ItemFactory(project=section.project, section=section, item_id='REQ-001')
        self.assertEqual(section.item_count, 1)


class ItemModelTest(TestCase):

    def test_search_queryset(self):
        project = ProjectFactory()
        section = SectionFactory(project=project)
        i1 = ItemFactory(project=project, section=section, item_id='REQ-001', text='Login requirement')
        i2 = ItemFactory(project=project, section=section, item_id='REQ-002', text='Logout requirement')
        results = Item.objects.search('Login')
        self.assertIn(i1, results)
        self.assertNotIn(i2, results)

    def test_search_by_item_id(self):
        project = ProjectFactory()
        section = SectionFactory(project=project)
        i1 = ItemFactory(project=project, section=section, item_id='REQ-001', text='Test')
        results = Item.objects.search('REQ-001')
        self.assertIn(i1, results)


class TagModelTest(TestCase):

    def test_for_project(self):
        project = ProjectFactory()
        preset = TagFactory(is_preset=True, project=None, name='Security')
        custom = TagFactory(project=project, name='Custom Tag')
        other = TagFactory(project=ProjectFactory(), name='Other')
        tags = Tag.for_project(project)
        self.assertIn(preset, tags)
        self.assertIn(custom, tags)
        self.assertNotIn(other, tags)


class AttachmentModelTest(TestCase):

    def test_file_size_display_bytes(self):
        att = AttachmentFactory(file_size=500)
        self.assertEqual(att.file_size_display, '500 B')

    def test_file_size_display_kb(self):
        att = AttachmentFactory(file_size=2048)
        self.assertEqual(att.file_size_display, '2.0 KB')

    def test_file_size_display_mb(self):
        att = AttachmentFactory(file_size=2 * 1024 * 1024)
        self.assertEqual(att.file_size_display, '2.0 MB')

    def test_file_type_icon_pdf(self):
        att = AttachmentFactory(filename='doc.pdf')
        self.assertIn('pdf', att.file_type_icon)

    def test_file_type_icon_unknown(self):
        att = AttachmentFactory(filename='file.xyz')
        self.assertIn('text-muted', att.file_type_icon)
