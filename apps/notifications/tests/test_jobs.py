from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.administration.factories import SystemSettingsFactory
from apps.notifications.factories import AuditLogFactory, NotificationFactory
from apps.notifications.jobs import (
    auto_archive_projects,
    auto_delete_archived,
    send_email_notification,
    send_weekly_digest,
)
from apps.notifications.models import AuditLog
from apps.projects.factories import (
    OwnedProjectFactory,
    ProjectFactory,
    ProjectMembershipFactory,
)
from apps.projects.models import Project


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='noreply@arcspec.test',
)
class SendEmailNotificationTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.user.settings.notify_comments = True
        self.user.settings.notify_status_changes = True
        self.user.settings.notify_collaborator_changes = True
        self.user.settings.save()

    def test_sends_email_on_comment_notification(self):
        notification = NotificationFactory(
            user=self.user,
            type='comment',
            message='New comment on REQ-001 in Test Project',
            link='/projects/test-project/',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('REQ-001', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_sends_email_on_status_change_notification(self):
        notification = NotificationFactory(
            user=self.user,
            type='status_changed',
            message='REQ-042 status changed to Approved in My Project',
            link='/projects/my-project/',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('REQ-042', mail.outbox[0].body)
        self.assertIn('My Project', mail.outbox[0].body)

    def test_sends_email_on_collaborator_added_notification(self):
        notification = NotificationFactory(
            user=self.user,
            type='collaborator_added',
            message='You were added to Test Project as Editor',
            link='/projects/test-project/',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Test Project', mail.outbox[0].body)

    def test_respects_notify_comments_disabled(self):
        self.user.settings.notify_comments = False
        self.user.settings.save()
        notification = NotificationFactory(
            user=self.user,
            type='comment',
            message='New comment on REQ-001 in Test Project',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 0)

    def test_new_item_emails_follow_the_new_items_switch(self):
        self.user.settings.notify_project_updates = False
        self.user.settings.notify_status_changes = True
        self.user.settings.save()
        notification = NotificationFactory(
            user=self.user,
            type='item_created',
            message='New item REQ-001 created in Test Project',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 0)
        self.user.settings.notify_project_updates = True
        self.user.settings.save()
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 1)

    def test_respects_notify_status_changes_disabled(self):
        self.user.settings.notify_status_changes = False
        self.user.settings.save()
        notification = NotificationFactory(
            user=self.user,
            type='status_changed',
            message='REQ-001 status changed to Approved',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 0)

    def test_respects_notify_collaborator_changes_disabled(self):
        self.user.settings.notify_collaborator_changes = False
        self.user.settings.save()
        notification = NotificationFactory(
            user=self.user,
            type='collaborator_added',
            message='You were added to Test Project',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_subject_contains_notification_type(self):
        notification = NotificationFactory(
            user=self.user,
            type='comment',
            message='New comment on REQ-001',
        )
        send_email_notification(notification)
        self.assertTrue(mail.outbox[0].subject.startswith('ArcSpec - '))
        self.assertIn('Comment', mail.outbox[0].subject)

    def test_user_without_settings_does_not_crash(self):
        user_no_settings = UserFactory()
        user_no_settings.settings.delete()
        notification = NotificationFactory(
            user=user_no_settings,
            type='comment',
            message='Test message',
        )
        send_email_notification(notification)
        self.assertEqual(len(mail.outbox), 1)

    def test_failed_send_is_logged_and_does_not_raise(self):
        notification = NotificationFactory(user=self.user, type='comment', message='Test message')
        with patch('apps.notifications.jobs.send_mail', side_effect=OSError('smtp down')), \
                self.assertLogs('apps.notifications.jobs', 'ERROR') as logs:
            send_email_notification(notification)
        self.assertIn(str(notification.pk), logs.output[0])
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='noreply@arcspec.test',
)
class SendWeeklyDigestTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.user.settings.notify_weekly_digest = True
        self.user.settings.save()
        self.project = OwnedProjectFactory(created_by=self.user)

    def test_sends_digest_to_opted_in_user(self):
        AuditLogFactory(
            project=self.project,
            user=self.user,
            action='created',
            target_type='Item',
            target_id='REQ-001',
        )
        send_weekly_digest()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_does_not_send_to_opted_out_user(self):
        self.user.settings.notify_weekly_digest = False
        self.user.settings.save()
        AuditLogFactory(
            project=self.project,
            user=self.user,
            action='created',
            target_type='Item',
            target_id='REQ-001',
        )
        send_weekly_digest()
        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_send_empty_digest(self):
        send_weekly_digest()
        self.assertEqual(len(mail.outbox), 0)

    def test_aggregates_activity_across_user_projects(self):
        project2 = OwnedProjectFactory(created_by=self.user)
        AuditLogFactory(project=self.project, user=self.user, action='created',
                        target_type='Item', target_id='REQ-001')
        AuditLogFactory(project=project2, user=self.user, action='status_changed',
                        target_type='Item', target_id='TC-001')
        send_weekly_digest()
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(self.project.name, body)
        self.assertIn(project2.name, body)

    def test_includes_collaborator_projects(self):
        other_user = UserFactory()
        other_project = ProjectFactory(created_by=other_user)
        ProjectMembershipFactory(project=other_project, user=self.user, role='editor')
        AuditLogFactory(project=other_project, user=other_user, action='created',
                        target_type='Item', target_id='REQ-001')
        send_weekly_digest()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(other_project.name, mail.outbox[0].body)

    def test_old_activity_excluded(self):
        log = AuditLogFactory(
            project=self.project,
            user=self.user,
            action='created',
            target_type='Item',
            target_id='REQ-001',
        )
        AuditLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        send_weekly_digest()
        self.assertEqual(len(mail.outbox), 0)

    def test_digest_email_subject(self):
        AuditLogFactory(project=self.project, user=self.user, action='created',
                        target_type='Item', target_id='REQ-001')
        send_weekly_digest()
        self.assertIn('Weekly Digest', mail.outbox[0].subject)


class AutoArchiveProjectsTest(TestCase):

    def test_archives_inactive_project(self):
        SystemSettingsFactory(
            auto_archive_enabled=True,
            auto_archive_days=30,
        )
        project = ProjectFactory(status='active')
        Project.objects.filter(pk=project.pk).update(
            updated_at=timezone.now() - timedelta(days=31)
        )
        auto_archive_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, 'archived')
        self.assertIsNotNone(project.archived_at)

    def test_audit_row_names_the_archived_project(self):
        SystemSettingsFactory(auto_archive_enabled=True, auto_archive_days=30)
        project = ProjectFactory(status='active', name='Clinic Booking Requirements')
        Project.objects.filter(pk=project.pk).update(updated_at=timezone.now() - timedelta(days=31))
        auto_archive_projects()
        log = AuditLog.objects.get(project=project, action='archived')
        self.assertEqual((log.target_type, log.target_id), ('Project', 'Clinic Booking Requirements'))

    def test_does_not_archive_recently_active_project(self):
        SystemSettingsFactory(auto_archive_enabled=True, auto_archive_days=30)
        project = ProjectFactory(status='active')
        auto_archive_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, 'active')

    def test_skips_already_archived_projects(self):
        SystemSettingsFactory(auto_archive_enabled=True, auto_archive_days=30)
        archived_at = timezone.now() - timedelta(days=5)
        project = ProjectFactory(status='archived')
        Project.objects.filter(pk=project.pk).update(
            updated_at=timezone.now() - timedelta(days=31),
            archived_at=archived_at,
        )
        auto_archive_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, 'archived')
        self.assertEqual(project.archived_at, archived_at)

    def test_does_nothing_when_feature_disabled(self):
        SystemSettingsFactory(auto_archive_enabled=False, auto_archive_days=30)
        project = ProjectFactory(status='active')
        Project.objects.filter(pk=project.pk).update(
            updated_at=timezone.now() - timedelta(days=31)
        )
        auto_archive_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, 'active')

    def test_does_nothing_when_days_is_zero(self):
        SystemSettingsFactory(auto_archive_enabled=True, auto_archive_days=0)
        project = ProjectFactory(status='active')
        Project.objects.filter(pk=project.pk).update(
            updated_at=timezone.now() - timedelta(days=100)
        )
        auto_archive_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, 'active')

    def test_creates_audit_log_for_archived_project(self):
        SystemSettingsFactory(auto_archive_enabled=True, auto_archive_days=30)
        project = ProjectFactory(status='active')
        Project.objects.filter(pk=project.pk).update(
            updated_at=timezone.now() - timedelta(days=31)
        )
        auto_archive_projects()
        log = AuditLog.objects.filter(project=project, action='archived').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_type, 'Project')
        self.assertIn('auto', log.details.get('reason', ''))

    def test_does_not_archive_draft_or_in_review(self):
        SystemSettingsFactory(auto_archive_enabled=True, auto_archive_days=30)
        draft = ProjectFactory(status='draft')
        in_review = ProjectFactory(status='in-review')
        Project.objects.filter(pk__in=[draft.pk, in_review.pk]).update(
            updated_at=timezone.now() - timedelta(days=31)
        )
        auto_archive_projects()
        draft.refresh_from_db()
        in_review.refresh_from_db()
        self.assertEqual(draft.status, 'draft')
        self.assertEqual(in_review.status, 'in-review')


class AutoDeleteArchivedTest(TestCase):

    def test_deletes_archived_project_past_threshold(self):
        SystemSettingsFactory(auto_delete_archived=True, auto_delete_days=365)
        project = ProjectFactory(status='archived')
        Project.objects.filter(pk=project.pk).update(
            archived_at=timezone.now() - timedelta(days=366)
        )
        auto_delete_archived()
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_does_not_delete_recently_archived_project(self):
        SystemSettingsFactory(auto_delete_archived=True, auto_delete_days=365)
        project = ProjectFactory(status='archived')
        Project.objects.filter(pk=project.pk).update(
            archived_at=timezone.now() - timedelta(days=10)
        )
        auto_delete_archived()
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_does_not_delete_active_projects(self):
        SystemSettingsFactory(auto_delete_archived=True, auto_delete_days=365)
        project = ProjectFactory(status='active')
        Project.objects.filter(pk=project.pk).update(
            updated_at=timezone.now() - timedelta(days=400)
        )
        auto_delete_archived()
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_does_nothing_when_feature_disabled(self):
        SystemSettingsFactory(auto_delete_archived=False, auto_delete_days=365)
        project = ProjectFactory(status='archived')
        Project.objects.filter(pk=project.pk).update(
            archived_at=timezone.now() - timedelta(days=400)
        )
        auto_delete_archived()
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_does_nothing_when_days_is_zero(self):
        SystemSettingsFactory(auto_delete_archived=True, auto_delete_days=0)
        project = ProjectFactory(status='archived')
        Project.objects.filter(pk=project.pk).update(
            archived_at=timezone.now() - timedelta(days=400)
        )
        auto_delete_archived()
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_does_not_delete_project_without_archived_at(self):
        SystemSettingsFactory(auto_delete_archived=True, auto_delete_days=365)
        project = ProjectFactory(status='archived')
        auto_delete_archived()
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())
