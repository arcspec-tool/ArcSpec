from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase

from apps.accounts.factories import UserFactory
from apps.notifications.models import AuditLog, Notification
from apps.projects.factories import AttachmentFactory, ItemFactory, ProjectFactory, ProjectMembershipFactory, SectionFactory
from apps.projects.models import ProjectVersion, Section

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


class DeleteAttributionTests(TestCase):

    def setUp(self):
        self.creator = UserFactory()
        self.actor = UserFactory()
        self.project = ProjectFactory(created_by=self.creator)
        ProjectMembershipFactory(project=self.project, user=self.actor, role='editor')
        self.section = SectionFactory(project=self.project)

    def audit(self, **filters):
        return AuditLog.objects.filter(project=self.project, **filters)

    def test_an_item_delete_names_the_actor(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.creator)
        item._actor = self.actor
        item.delete()
        self.assertEqual(self.audit(action='deleted', target_type='Item').get().user, self.actor)

    def test_an_item_delete_without_an_actor_names_the_creator(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.creator)
        item.delete()
        self.assertEqual(self.audit(action='deleted', target_type='Item').get().user, self.creator)

    def test_section_changes_name_the_actor(self):
        section = Section(project=self.project, title='New', number='9', order=9)
        section._actor = self.actor
        section.save()
        self.assertEqual(self.audit(action='created', target_type='Section', target_id='9').get().user, self.actor)
        section.title = 'Renamed'
        section._actor = self.actor
        section.save()
        self.assertEqual(self.audit(action='updated', target_type='Section', target_id='9').get().user, self.actor)
        section._actor = self.actor
        section.delete()
        self.assertEqual(self.audit(action='deleted', target_type='Section', target_id='9').get().user, self.actor)

    def test_silent_saves_and_deletes_write_nothing(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.creator)
        self.audit().delete()
        Notification.objects.all().delete()
        versions = ProjectVersion.objects.filter(project=self.project).count()
        item.status = 'approved'
        item._silent = True
        item.save()
        item._silent = True
        item.delete()
        section = Section(project=self.project, title='Quiet', number='8', order=8)
        section._silent = True
        section.save()
        section._silent = True
        section.delete()
        self.assertEqual(self.audit().count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(ProjectVersion.objects.filter(project=self.project).count(), versions)


class FileRemovalTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(created_by=self.user)
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        self.item.image = SimpleUploadedFile('pic.png', PNG, content_type='image/png')
        self.item._silent = True
        self.item.save()
        self.attachment = AttachmentFactory(item=self.item, uploaded_by=self.user)
        self.storage = self.item.image.storage
        self.image_name = self.item.image.name
        self.attachment_name = self.attachment.file.name

    def test_deleting_an_item_removes_its_files_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.item.delete()
        self.assertFalse(self.storage.exists(self.image_name))
        self.assertFalse(self.storage.exists(self.attachment_name))

    def test_deleting_a_project_removes_its_files(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.project.delete()
        self.assertFalse(self.storage.exists(self.image_name))
        self.assertFalse(self.storage.exists(self.attachment_name))

    def test_a_rolled_back_delete_keeps_the_files(self):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.item.delete()
                    raise RuntimeError('undo')
            except RuntimeError:
                pass
        self.assertTrue(self.storage.exists(self.image_name))
        self.assertTrue(self.storage.exists(self.attachment_name))
