from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.notifications.models import AuditLog, Notification
from apps.projects.factories import (
    AttachmentFactory,
    CommentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TagFactory,
)
from apps.projects.models import Item, ItemAttributeValue, ItemTag, ProjectAttribute, ProjectVersion, Section
from apps.projects.signals import create_version

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


class RestoreFixture:

    def build(self):
        self.admin = UserFactory()
        self.member = UserFactory()
        self.project = ProjectFactory(created_by=self.admin)
        ProjectMembershipFactory(project=self.project, user=self.admin, role='admin')
        ProjectMembershipFactory(project=self.project, user=self.member, role='editor')
        self.parent = SectionFactory(project=self.project, title='Parent', number='1', order=0, description='about')
        self.child = SectionFactory(project=self.project, title='Child', number='1.1', order=1, parent=self.parent)
        self.attribute = ProjectAttribute.objects.create(project=self.project, name='Owner', field_type='text', order=0)
        self.tag = TagFactory(project=self.project, name='core')
        self.first = ItemFactory(project=self.project, section=self.child, created_by=self.member, text='<p>first</p>', status='draft')
        self.second = ItemFactory(project=self.project, section=self.child, created_by=self.admin, text='<p>second</p>', status='draft')
        ItemAttributeValue.objects.create(item=self.first, attribute=self.attribute, value='alice')
        ItemTag.objects.create(item=self.first, tag=self.tag)
        self.first.image = SimpleUploadedFile('first.png', PNG, content_type='image/png')
        self.first._silent = True
        self.first.save()
        self.comment = CommentFactory(item=self.first, author=self.member)
        self.attachment = AttachmentFactory(item=self.first, uploaded_by=self.member)
        create_version(self.project, self.admin, 'baseline')
        self.version = ProjectVersion.objects.filter(project=self.project).order_by('-changed_at').first()
        self.url = reverse('api_version_restore', kwargs={'slug': self.project.slug, 'public_key': self.version.public_key})
        self.client.force_login(self.admin)

    def change_things(self):
        self.first.text = '<p>changed</p>'
        self.first.status = 'approved'
        self.first._actor = self.member
        self.first.save()
        self.first.attribute_values.update(value='bob')
        ItemTag.objects.filter(item=self.first).delete()
        self.extra = ItemFactory(project=self.project, section=self.parent, created_by=self.admin, text='<p>extra</p>')
        self.second_item_id = self.second.item_id
        self.second._actor = self.admin
        self.second.delete()
        later = SectionFactory(project=self.project, title='Later', number='2', order=2)
        SectionFactory(project=self.project, title='Later child', number='2.1', order=3, parent=later)
        self.child.title = 'Renamed'
        self.child.description = 'x'
        self.child.parent = None
        self.child.save()


class VersionRestoreTests(RestoreFixture, TestCase):

    def setUp(self):
        self.build()

    def test_restore_puts_rows_back_without_replacing_the_ones_that_still_exist(self):
        self.change_things()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        first = Item.objects.get(pk=self.first.pk)
        self.assertEqual(first.text, '<p>first</p>')
        self.assertEqual(first.status, 'draft')
        self.assertEqual(first.created_by, self.member)
        self.assertEqual(first.image.name, self.first.image.name)
        self.assertEqual(first.comments.count(), 1)
        self.assertEqual(first.attachments.count(), 1)
        self.assertEqual(list(first.attribute_values.values_list('value', flat=True)), ['alice'])
        self.assertEqual(list(first.item_tags.values_list('tag__name', flat=True)), ['core'])
        self.assertFalse(Item.objects.filter(pk=self.extra.pk).exists())
        second = Item.objects.get(project=self.project, item_id=self.second_item_id)
        self.assertEqual(second.text, '<p>second</p>')
        self.assertEqual(second.created_by, self.admin)
        child = Section.objects.get(pk=self.child.pk)
        self.assertEqual(child.title, 'Child')
        self.assertEqual(child.description, '')
        self.assertEqual(child.parent_id, self.parent.pk)
        self.assertEqual(Section.objects.get(pk=self.parent.pk).description, 'about')
        self.assertEqual(set(self.project.sections.values_list('title', flat=True)), {'Parent', 'Child'})

    def test_restore_writes_one_audit_row_and_one_version_and_sends_nothing(self):
        self.change_things()
        AuditLog.objects.filter(project=self.project).delete()
        Notification.objects.all().delete()
        versions = ProjectVersion.objects.filter(project=self.project).count()
        mail.outbox = []
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        rows = list(AuditLog.objects.filter(project=self.project))
        self.assertEqual([(row.action, row.user_id) for row in rows], [('version_restored', self.admin.pk)])
        self.assertEqual(rows[0].details, {'version': self.version.version_number})
        self.assertEqual(ProjectVersion.objects.filter(project=self.project).count(), versions + 1)
        self.assertEqual(ProjectVersion.objects.filter(project=self.project).order_by('-changed_at').first().change_summary, f'Restored version {self.version.version_number}')
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_restore_removes_the_files_of_the_items_it_deletes(self):
        extra = ItemFactory(project=self.project, section=self.parent, created_by=self.admin)
        extra.image = SimpleUploadedFile('extra.png', PNG, content_type='image/png')
        extra._silent = True
        extra.save()
        storage, name = extra.image.storage, extra.image.name
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url).status_code, 200)
        self.assertFalse(storage.exists(name))
        self.assertTrue(storage.exists(self.first.image.name))

    def test_restore_still_refuses_an_editor(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.url).status_code, 403)


class VersionRestoreCommitTests(RestoreFixture, TransactionTestCase):

    def setUp(self):
        self.build()

    def test_restore_skips_values_whose_attribute_or_tag_is_gone(self):
        self.attribute.delete()
        self.tag.delete()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        first = Item.objects.get(pk=self.first.pk)
        self.assertEqual(first.attribute_values.count(), 0)
        self.assertEqual(first.item_tags.count(), 0)
        self.assertEqual(first.text, '<p>first</p>')
