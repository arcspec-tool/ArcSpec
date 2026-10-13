import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core.site import absolute_url

logger = logging.getLogger(__name__)


NOTIFICATION_PREFERENCE_MAP = {
    'item_created': 'notify_project_updates',
    'comment': 'notify_comments',
    'status_changed': 'notify_status_changes',
    'collaborator_added': 'notify_collaborator_changes',
    'mention': 'notify_comments',
    'review_requested': 'notify_project_updates',
}


def _user_wants_email(user, notification_type):
    from apps.accounts.models import UserSettings
    try:
        user_settings = user.settings
    except UserSettings.DoesNotExist:
        return True
    pref_field = NOTIFICATION_PREFERENCE_MAP.get(notification_type, 'notify_project_updates')
    return getattr(user_settings, pref_field, True)


def send_email_notification(notification):
    if not _user_wants_email(notification.user, notification.type):
        return

    subject = _('ArcSpec - %(type)s') % {'type': notification.get_type_display()}
    context = {
        'notification': notification,
        'user': notification.user,
    }
    html_body = render_to_string('notifications/emails/notification.html', context)
    plain_body = notification.message
    if notification.link:
        plain_body += '\n\n' + _('View in ArcSpec: %(url)s') % {'url': absolute_url(notification.link)}

    try:
        send_mail(
            subject=subject,
            message=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.user.email],
            html_message=html_body,
        )
    except Exception:
        logger.exception("Failed to send email for notification %s", notification.pk)


def send_weekly_digest():
    from apps.accounts.models import User
    from apps.notifications.models import AuditLog

    cutoff = timezone.now() - timedelta(days=7)

    opted_in_users = User.objects.filter(
        is_active=True,
        settings__notify_weekly_digest=True,
    ).select_related('settings')

    for user in opted_in_users:
        user_projects = _get_user_projects(user)
        if not user_projects:
            continue

        activity = AuditLog.objects.filter(
            project__in=user_projects,
            created_at__gte=cutoff,
        ).select_related('project').order_by('-created_at')

        if not activity.exists():
            continue

        project_activity = {}
        for log in activity:
            project_name = log.project.name
            if project_name not in project_activity:
                project_activity[project_name] = []
            project_activity[project_name].append(log)

        context = {
            'user': user,
            'project_activity': project_activity,
            'period_start': cutoff,
            'period_end': timezone.now(),
        }
        html_body = render_to_string('notifications/emails/weekly_digest.html', context)

        plain_lines = [_('Weekly Digest for %(name)s') % {'name': user.get_full_name() or user.email}, ""]
        for project_name, logs in project_activity.items():
            plain_lines.append(ngettext(
                '%(project)s: %(count)d changes, %(url)s',
                '%(project)s: %(count)d changes, %(url)s',
                len(logs),
            ) % {'project': project_name, 'count': len(logs), 'url': absolute_url(logs[0].project.get_absolute_url())})
        plain_lines += ["", _('Open dashboard: %(url)s') % {'url': absolute_url(reverse('dashboard:dashboard'))}]
        plain_body = "\n".join(plain_lines)

        try:
            send_mail(
                subject=_('ArcSpec - Weekly Digest'),
                message=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_body,
            )
        except Exception:
            logger.exception("Failed to send weekly digest to user %s", user.pk)


def _get_user_projects(user):
    from apps.projects.models import Project
    return Project.objects.filter(memberships__user=user)


def auto_archive_projects():
    from apps.administration.models import SystemSettings
    from apps.notifications.models import AuditLog

    system_settings = SystemSettings.load()

    if not system_settings.auto_archive_enabled:
        return

    if system_settings.auto_archive_days == 0:
        return

    from apps.projects.models import Project

    threshold = timezone.now() - timedelta(days=system_settings.auto_archive_days)
    stale_projects = Project.objects.filter(status='active', updated_at__lt=threshold)

    now = timezone.now()
    for project in stale_projects:
        Project.objects.filter(pk=project.pk).update(
            status='archived',
            archived_at=now,
        )
        AuditLog.objects.create(
            project=project,
            user=project.created_by,
            action='archived',
            target_type='Project',
            target_id=project.name[:50],
            details={'reason': 'auto-archived due to inactivity'},
        )
        logger.info("Auto-archived project %s (pk=%s)", project.name, project.pk)


def auto_delete_archived():
    from apps.administration.models import SystemSettings
    from apps.projects.models import Project

    system_settings = SystemSettings.load()

    if not system_settings.auto_delete_archived:
        return

    if system_settings.auto_delete_days == 0:
        return

    threshold = timezone.now() - timedelta(days=system_settings.auto_delete_days)
    old_archived = Project.objects.filter(
        status='archived',
        archived_at__isnull=False,
        archived_at__lt=threshold,
    )

    for project in old_archived:
        logger.info("Auto-deleting archived project %s (pk=%s)", project.name, project.pk)
        project.delete()
