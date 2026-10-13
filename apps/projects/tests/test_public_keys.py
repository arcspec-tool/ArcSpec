from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import (
    AttachmentFactory,
    ItemFactory,
    ProjectAttributeFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)
from apps.projects.models import ProjectAttribute


class AttachmentDownloadTest(TestCase):

    def setUp(self):
        self.member = UserFactory()
        self.project = ProjectFactory(created_by=self.member)
        ProjectMembershipFactory(project=self.project, user=self.member, role='editor')
        section = SectionFactory(project=self.project)
        item = ItemFactory(project=self.project, section=section, created_by=self.member)
        self.attachment = AttachmentFactory(item=item, uploaded_by=self.member, file__data=b'%PDF-1.4 test')
        self.url = reverse('attachment_download', kwargs={'slug': self.project.slug, 'public_key': self.attachment.public_key})

    def test_a_member_downloads_the_file_by_its_public_key(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4 test')

    def test_a_non_member_is_refused(self):
        self.client.force_login(UserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_an_attachment_of_another_project_is_404_under_this_slug(self):
        other = ProjectFactory(created_by=self.member)
        ProjectMembershipFactory(project=other, user=self.member, role='editor')
        self.client.force_login(self.member)
        url = reverse('attachment_download', kwargs={'slug': other.slug, 'public_key': self.attachment.public_key})
        self.assertEqual(self.client.get(url).status_code, 404)


class ProjectAttributeDetailTest(TestCase):

    def setUp(self):
        self.editor = UserFactory()
        self.project = ProjectFactory(created_by=self.editor)
        ProjectMembershipFactory(project=self.project, user=self.editor, role='editor')
        self.attribute = ProjectAttributeFactory(project=self.project, name='Risk')
        self.url = reverse('api_project_attribute_detail', kwargs={'slug': self.project.slug, 'public_key': self.attribute.public_key})
        self.client.force_login(self.editor)

    def test_patch_renames_by_public_key_and_returns_it(self):
        response = self.client.patch(self.url, {'name': 'Hazard'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['name'], 'Hazard')
        self.assertEqual(response.json()['public_key'], str(self.attribute.public_key))
        self.attribute.refresh_from_db()
        self.assertEqual(self.attribute.name, 'Hazard')

    def test_patch_refuses_a_name_already_taken(self):
        ProjectAttributeFactory(project=self.project, name='Taken')
        response = self.client.patch(self.url, {'name': 'Taken'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_by_public_key(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProjectAttribute.objects.filter(pk=self.attribute.pk).exists())

    def test_builtin_attributes_are_protected(self):
        builtin = ProjectAttributeFactory(project=self.project, name='Status', is_builtin=True)
        url = reverse('api_project_attribute_detail', kwargs={'slug': self.project.slug, 'public_key': builtin.public_key})
        self.assertEqual(self.client.patch(url, {'name': 'X'}, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)

    def test_the_list_carries_each_public_key(self):
        response = self.client.get(reverse('api_project_attribute_list', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(self.attribute.public_key), [a['public_key'] for a in response.json()])

    def test_a_viewer_cannot_change_attributes(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
