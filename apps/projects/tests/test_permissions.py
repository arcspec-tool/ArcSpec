import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import (
    CommentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    ProjectVersionFactory,
    SectionFactory,
    TagFactory,
)


class NonMemberAccessTests(TestCase):

    def setUp(self):
        self.project = ProjectFactory()
        self.section = SectionFactory(project=self.project)
        self.non_member = UserFactory()
        self.client.force_login(self.non_member)

    def test_a_non_member_gets_404_on_every_project_route(self):
        slug = {'slug': self.project.slug}
        for name in ('api_item_list', 'api_section_list', 'api_collaborator_list', 'api_tag_list', 'api_audit_log', 'api_version_list', 'project_detail'):
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name, kwargs=slug)).status_code, 404)


class SystemAdminAccessTests(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.project = ProjectFactory()
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=UserFactory()
        )
        self.client.force_login(self.admin)

    def test_sysadmin_can_invite_collaborator(self):
        new_user = UserFactory()
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': new_user.email, 'role': 'editor',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_sysadmin_can_restore_version(self):
        version = ProjectVersionFactory(
            project=self.project, changed_by=self.admin
        )
        url = reverse('api_version_restore', kwargs={
            'slug': self.project.slug, 'public_key': version.public_key
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)


class AdminFullControlTests(TestCase):

    def setUp(self):
        self.admin_user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.admin_user, role='admin')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.admin_user
        )
        self.client.force_login(self.admin_user)

    def test_admin_can_delete_others_comment(self):
        other = UserFactory()
        ProjectMembershipFactory(project=self.project, user=other, role='editor')
        comment = CommentFactory(item=self.item, author=other)
        url = reverse('api_comment_delete', kwargs={
            'slug': self.project.slug, 'public_key': comment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)


class EditorPermissionTests(TestCase):

    def setUp(self):
        self.editor = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.editor, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.editor
        )
        self.client.force_login(self.editor)

    def test_editor_can_update_item_tags(self):
        tag = TagFactory(project=self.project, name='Bug')
        url = reverse('api_item_tags', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        response = self.client.put(url, data=json.dumps({
            'tag_ids': [tag.pk],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_editor_cannot_change_collaborator_role(self):
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='viewer')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'role': 'editor',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_editor_cannot_remove_collaborator(self):
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='viewer')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_editor_cannot_delete_others_comment(self):
        other = UserFactory()
        ProjectMembershipFactory(project=self.project, user=other, role='editor')
        comment = CommentFactory(item=self.item, author=other)
        url = reverse('api_comment_delete', kwargs={
            'slug': self.project.slug, 'public_key': comment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)


class ViewerRoleEnforcementTests(TestCase):

    def setUp(self):
        self.editor = UserFactory()
        self.viewer = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.editor, role='editor')
        ProjectMembershipFactory(project=self.project, user=self.viewer, role='viewer')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.editor
        )
        self.client.force_login(self.viewer)

    def test_viewer_can_delete_own_comment(self):
        comment = CommentFactory(item=self.item, author=self.viewer)
        url = reverse('api_comment_delete', kwargs={
            'slug': self.project.slug, 'public_key': comment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_viewer_can_export(self):
        url = reverse('project_export', kwargs={'slug': self.project.slug})
        response = self.client.post(url, {'format': 'pdf'})
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_update_item(self):
        url = reverse('api_item_detail', kwargs={
            'slug': self.project.slug, 'public_key': self.item.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'text': 'Hacked text',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_update_item_tags(self):
        tag = TagFactory(project=self.project, name='Bug')
        url = reverse('api_item_tags', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        response = self.client.put(url, data=json.dumps({
            'tag_ids': [tag.pk],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_invite_collaborator(self):
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': UserFactory().email, 'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_change_collaborator_role(self):
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='editor')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_remove_collaborator(self):
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='editor')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_restore_version(self):
        version = ProjectVersionFactory(
            project=self.project, changed_by=self.editor
        )
        url = reverse('api_version_restore', kwargs={
            'slug': self.project.slug, 'public_key': version.public_key
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_delete_others_comment(self):
        comment = CommentFactory(item=self.item, author=self.editor)
        url = reverse('api_comment_delete', kwargs={
            'slug': self.project.slug, 'public_key': comment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)
