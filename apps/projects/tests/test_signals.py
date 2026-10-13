from django.test import TestCase

from apps.accounts.factories import UserFactory
from apps.notifications.models import AuditLog, Notification
from apps.projects.factories import (
    OwnedProjectFactory,
    CommentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)
from apps.projects.models import Project, ProjectVersion


class AuditLogSignalTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(created_by=self.user)
        self.section = SectionFactory(project=self.project)

    def test_project_delete_cascades_children_sharing_its_primary_key(self):
        pk = 970001
        project = ProjectFactory(pk=pk, created_by=self.user)
        section = SectionFactory(pk=pk, project=project)
        ItemFactory(pk=pk, project=project, section=section, created_by=self.user)
        ProjectMembershipFactory(pk=pk, project=project, user=UserFactory(), role='viewer', added_by=self.user)
        AuditLog.objects.all().delete()
        Notification.objects.all().delete()
        project.delete()
        self.assertFalse(Project.objects.filter(pk=pk).exists())
        self.assertEqual(AuditLog.objects.filter(project_id=pk).count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_notifications_carry_the_project_and_go_with_it(self):
        member = UserFactory()
        ProjectMembershipFactory(project=self.project, user=member, role='editor', added_by=self.user)
        item = ItemFactory(project=self.project, section=self.section, created_by=self.user, status='draft')
        item.status = 'approved'
        item._actor = member
        item.save()
        CommentFactory(item=item, author=member, text='A comment')
        own = Notification.objects.filter(project=self.project)
        self.assertGreaterEqual(own.count(), 3)
        self.assertEqual(Notification.objects.filter(link__startswith=f'/projects/{self.project.slug}/', project__isnull=True).count(), 0)
        unrelated = Notification.objects.create(user=self.user, type='mention', message='keep me', link='/dashboard/')
        self.project.delete()
        self.assertEqual(Notification.objects.filter(link__startswith=f'/projects/{self.project.slug}/').count(), 0)
        self.assertTrue(Notification.objects.filter(pk=unrelated.pk).exists())

    def test_direct_child_deletes_still_write_audit_rows(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        AuditLog.objects.filter(project=self.project).delete()
        item.delete()
        self.assertEqual(AuditLog.objects.filter(project=self.project, action='deleted', target_type='Item').count(), 1)
        Project.objects.filter(pk=self.project.pk).delete()
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_audit_log_created_on_item_create(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        log = AuditLog.objects.filter(
            project=self.project, action='created', target_type='Item'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.target_id, item.item_id)

    def test_audit_log_created_on_item_update(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        AuditLog.objects.all().delete()
        item.text = 'Updated text'
        item.save()
        log = AuditLog.objects.filter(
            project=self.project, action='updated', target_type='Item'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_id, item.item_id)

    def test_audit_log_created_on_item_status_change(self):
        item = ItemFactory(
            project=self.project, section=self.section,
            created_by=self.user, status='draft'
        )
        AuditLog.objects.all().delete()
        item.status = 'approved'
        item.save()
        log = AuditLog.objects.filter(
            project=self.project, action='status_changed', target_type='Item'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['old_status'], 'draft')
        self.assertEqual(log.details['new_status'], 'approved')

    def test_audit_log_created_on_item_priority_change(self):
        item = ItemFactory(
            project=self.project, section=self.section,
            created_by=self.user, priority='medium'
        )
        AuditLog.objects.all().delete()
        item.priority = 'high'
        item.save()
        log = AuditLog.objects.filter(
            project=self.project, action='priority_changed', target_type='Item'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['old_priority'], 'medium')
        self.assertEqual(log.details['new_priority'], 'high')

    def test_audit_log_created_on_item_delete(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        item_id = item.item_id
        AuditLog.objects.all().delete()
        item.delete()
        log = AuditLog.objects.filter(
            project=self.project, action='deleted', target_type='Item'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_id, item_id)

    def test_audit_log_created_on_section_create(self):
        section = SectionFactory(project=self.project, title='New Section')
        log = AuditLog.objects.filter(
            project=self.project, action='created', target_type='Section'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['title'], 'New Section')

    def test_audit_log_created_on_section_update(self):
        section = SectionFactory(project=self.project, title='Original')
        AuditLog.objects.all().delete()
        section.title = 'Renamed'
        section.save()
        log = AuditLog.objects.filter(
            project=self.project, action='updated', target_type='Section'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['title'], 'Renamed')

    def test_audit_log_created_on_section_delete(self):
        section = SectionFactory(project=self.project, title='To Delete', number='99')
        section_number = section.number
        AuditLog.objects.all().delete()
        section.delete()
        log = AuditLog.objects.filter(
            project=self.project, action='deleted', target_type='Section'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_id, section_number)

    def test_audit_log_created_on_membership_create(self):
        other_user = UserFactory()
        membership = ProjectMembershipFactory(
            project=self.project, user=other_user, role='editor',
            added_by=self.user,
        )
        log = AuditLog.objects.filter(
            project=self.project, action='collaborator_added', target_type='User'
        ).first()
        self.assertEqual(log.target_id, str(other_user))
        self.assertEqual(log.details['user_email'], other_user.email)
        self.assertEqual(log.details['role'], 'editor')

    def test_audit_log_created_on_membership_role_change(self):
        other_user = UserFactory()
        membership = ProjectMembershipFactory(
            project=self.project, user=other_user, role='editor',
            added_by=self.user,
        )
        AuditLog.objects.all().delete()
        membership.role = 'admin'
        membership.save()
        log = AuditLog.objects.filter(
            project=self.project, action='collaborator_role_changed', target_type='User'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['old_role'], 'editor')
        self.assertEqual(log.details['new_role'], 'admin')

    def test_audit_log_created_on_membership_delete(self):
        other_user = UserFactory()
        membership = ProjectMembershipFactory(
            project=self.project, user=other_user, role='viewer',
            added_by=self.user,
        )
        AuditLog.objects.all().delete()
        membership.delete()
        log = AuditLog.objects.filter(
            project=self.project, action='collaborator_removed', target_type='User'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['user_email'], other_user.email)


class NotificationSignalTests(TestCase):

    def setUp(self):
        self.owner = UserFactory()
        self.project = OwnedProjectFactory(created_by=self.owner)
        self.section = SectionFactory(project=self.project)
        self.editor = UserFactory()
        ProjectMembershipFactory(
            project=self.project, user=self.editor, role='editor',
            added_by=self.owner,
        )
        Notification.objects.all().delete()

    def test_notification_created_on_comment(self):
        item = ItemFactory(
            project=self.project, section=self.section, created_by=self.owner
        )
        Notification.objects.all().delete()
        CommentFactory(item=item, author=self.editor, text='A comment')
        notifs = Notification.objects.filter(user=self.owner, type='comment')
        self.assertTrue(notifs.exists())

    def test_comment_author_does_not_get_self_notification(self):
        item = ItemFactory(
            project=self.project, section=self.section, created_by=self.editor
        )
        Notification.objects.all().delete()
        CommentFactory(item=item, author=self.editor, text='Self comment')
        notifs = Notification.objects.filter(user=self.editor, type='comment')
        self.assertFalse(notifs.exists())

    def test_a_new_item_notifies_the_other_members_as_item_created(self):
        ItemFactory(project=self.project, section=self.section, created_by=self.owner)
        notifications = Notification.objects.filter(message__startswith='New item ')
        self.assertTrue(notifications.exists())
        self.assertEqual(set(notifications.values_list('type', flat=True)), {'item_created'})

    def test_notification_created_on_status_change(self):
        item = ItemFactory(
            project=self.project, section=self.section,
            created_by=self.owner, status='draft'
        )
        Notification.objects.all().delete()
        item.status = 'in-review'
        item.save()
        notifs = Notification.objects.filter(type='status_changed')
        self.assertTrue(notifs.exists())

    def test_status_change_through_the_api_names_the_editor_as_actor(self):
        import json

        from django.urls import reverse

        item = ItemFactory(
            project=self.project, section=self.section,
            created_by=self.owner, status='draft'
        )
        Notification.objects.all().delete()
        self.client.force_login(self.editor)
        url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': item.public_key})
        response = self.client.patch(url, json.dumps({'field': 'status', 'value': 'approved'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        to_owner = Notification.objects.filter(user=self.owner, type='status_changed')
        self.assertEqual(to_owner.count(), 1)
        self.assertEqual(to_owner.get().actor, self.editor)
        self.assertFalse(Notification.objects.filter(user=self.editor, type='status_changed').exists())
        audit = AuditLog.objects.filter(project=self.project, action='status_changed', target_id=item.item_id).latest('created_at')
        self.assertEqual(audit.user, self.editor)

    def test_creator_removed_from_the_project_receives_no_item_notification(self):
        self.project.memberships.get(user=self.owner).delete()
        Notification.objects.all().delete()
        ItemFactory(project=self.project, section=self.section, created_by=self.editor)
        self.assertFalse(Notification.objects.filter(user=self.owner).exists())

    def test_notification_created_on_collaborator_add(self):
        new_user = UserFactory()
        Notification.objects.all().delete()
        ProjectMembershipFactory(
            project=self.project, user=new_user, role='viewer',
            added_by=self.owner,
        )
        notif = Notification.objects.filter(
            user=new_user, type='collaborator_added'
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn(self.project.name, notif.message)
        self.assertEqual(Notification.objects.filter(user=new_user).count(), 1)
        self.assertIn('You were added', notif.message)
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 0)
        others = Notification.objects.exclude(user__in=[new_user, self.owner])
        self.assertTrue(all(n.message.endswith('as Viewer') and 'was added' in n.message for n in others))

    def test_notification_has_link(self):
        new_user = UserFactory()
        Notification.objects.all().delete()
        ProjectMembershipFactory(
            project=self.project, user=new_user, role='viewer',
            added_by=self.owner,
        )
        notif = Notification.objects.filter(user=new_user, type='collaborator_added').first()
        self.assertIsNotNone(notif)
        self.assertIn(self.project.slug, notif.link)


class ProjectVersionSignalTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(created_by=self.user)
        self.section = SectionFactory(project=self.project)

    def test_version_created_on_item_create(self):
        ItemFactory(project=self.project, section=self.section, created_by=self.user)
        version = ProjectVersion.objects.filter(project=self.project).first()
        self.assertIsNotNone(version)
        self.assertEqual(version.changed_by, self.user)

    def test_version_number_increments(self):
        ItemFactory(project=self.project, section=self.section, created_by=self.user)
        ItemFactory(project=self.project, section=self.section, created_by=self.user)
        versions = ProjectVersion.objects.filter(project=self.project).order_by('changed_at')
        self.assertEqual(versions.count(), 2)
        self.assertNotEqual(versions[0].version_number, versions[1].version_number)

    def test_version_records_item_count(self):
        ItemFactory(project=self.project, section=self.section, created_by=self.user)
        ItemFactory(project=self.project, section=self.section, created_by=self.user)
        version = ProjectVersion.objects.filter(project=self.project).order_by('-changed_at').first()
        self.assertEqual(version.item_count, 2)

    def test_version_created_on_item_status_change(self):
        item = ItemFactory(
            project=self.project, section=self.section,
            created_by=self.user, status='draft'
        )
        ProjectVersion.objects.all().delete()
        item.status = 'in-review'
        item.save()
        version = ProjectVersion.objects.get(project=self.project)
        self.assertEqual(version.change_summary, f'Item {item.item_id} status changed to In Review')

    def test_version_created_on_item_delete(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        item_id = item.item_id
        ProjectVersion.objects.all().delete()
        item.delete()
        version = ProjectVersion.objects.filter(project=self.project).first()
        self.assertIsNotNone(version)
        self.assertIn(item_id, version.change_summary)
