from django.db import transaction
from django.db.models import QuerySet
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext as _

from apps.notifications.models import AuditLog, Notification
from apps.notifications.push import push_notification
from apps.projects.models import (
    Attachment,
    Comment,
    Item,
    ItemAttributeValue,
    ItemTag,
    Project,
    ProjectMembership,
    ProjectVersion,
    Section,
)


def _next_version_number(project):
    last = ProjectVersion.objects.filter(project=project).order_by('-changed_at').first()
    if last is None:
        return '0.1'
    parts = last.version_number.split('.')
    try:
        minor = int(parts[-1]) + 1
        return f"{parts[0]}.{minor}"
    except (ValueError, IndexError):
        return '0.1'


def _is_cascade_delete(instance, **kwargs):
    origin = kwargs.get('origin')
    if origin is None or origin is instance:
        return False
    if isinstance(origin, Project):
        return True
    return isinstance(origin, QuerySet) and origin.model is Project


def _silent(instance):
    return getattr(instance, '_silent', False)


def _actor(instance, fallback):
    return getattr(instance, '_actor', None) or fallback


def build_snapshot(project):
    sections = list(project.sections.values('id', 'parent_id', 'title', 'description', 'number', 'order'))
    items = list(project.items.values(
        'id', 'section_id', 'item_id', 'text', 'status', 'priority',
        'assignee_id', 'created_by_id', 'order', 'image_caption',
    ))
    item_tags = {}
    for it in ItemTag.objects.filter(item__project=project).values('item_id', 'tag_id'):
        item_tags.setdefault(it['item_id'], []).append(it['tag_id'])
    item_attrs = {}
    for av in ItemAttributeValue.objects.filter(item__project=project).values('item_id', 'attribute_id', 'value'):
        item_attrs.setdefault(av['item_id'], []).append({'attribute_id': av['attribute_id'], 'value': av['value']})
    for item in items:
        item['tag_ids'] = item_tags.get(item['id'], [])
        item['attribute_values'] = item_attrs.get(item['id'], [])
    return {'sections': sections, 'items': items}


def create_version(project, user, summary):
    ProjectVersion.objects.create(
        project=project,
        version_number=_next_version_number(project),
        changed_by=user,
        change_summary=summary,
        item_count=project.items.count(),
        snapshot=build_snapshot(project),
    )


def _project_collaborator_users(project, exclude_user=None, exclude_users=()):
    from apps.accounts.models import User
    user_ids = set(project.memberships.values_list('user_id', flat=True))
    for excluded in (exclude_user, *exclude_users):
        if excluded is not None:
            user_ids.discard(excluded.id)
    return User.objects.filter(id__in=user_ids)


def _notify_project_users(project, actor, notification_type, message, link=None, exclude=()):
    if link is None:
        link = project.get_absolute_url()
    for user in _project_collaborator_users(project, exclude_user=actor, exclude_users=exclude):
        notification = Notification.objects.create(
            user=user,
            actor=actor,
            project=project,
            type=notification_type,
            message=message,
            link=link,
        )
        push_notification(notification)


def _delete_file(field_file):
    if not field_file:
        return
    storage, name = field_file.storage, field_file.name
    transaction.on_commit(lambda: storage.delete(name))


@receiver(pre_save, sender=Item)
def item_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Item.objects.get(pk=instance.pk)
            instance._old_status = old.status
            instance._old_priority = old.priority
            instance._old_text = old.text
        except Item.DoesNotExist:
            instance._old_status = None
            instance._old_priority = None
            instance._old_text = None
    else:
        instance._old_status = None
        instance._old_priority = None
        instance._old_text = None


@receiver(post_save, sender=Item)
def item_post_save(sender, instance, created, **kwargs):
    if _silent(instance):
        return
    user = _actor(instance, instance.created_by)

    if created:
        AuditLog.objects.create(
            project=instance.project,
            user=user,
            action='created',
            target_type='Item',
            target_id=instance.item_id,
            details={'text': instance.text[:100]},
        )
        create_version(
            instance.project, user,
            _('Created item %(item)s') % {'item': instance.item_id}
        )
        _notify_project_users(
            instance.project, actor=user,
            notification_type='item_created',
            message=_('New item %(item)s created in %(project)s') % {'item': instance.item_id, 'project': instance.project.name},
        )
        return

    old_status = getattr(instance, '_old_status', None)
    if old_status and old_status != instance.status:
        AuditLog.objects.create(
            project=instance.project,
            user=user,
            action='status_changed',
            target_type='Item',
            target_id=instance.item_id,
            details={'old_status': old_status, 'new_status': instance.status},
        )
        _notify_project_users(
            instance.project, actor=user,
            notification_type='status_changed',
            message=_('%(item)s status changed to %(status)s in %(project)s') % {
                'item': instance.item_id,
                'status': instance.get_status_display(),
                'project': instance.project.name,
            },
        )
        create_version(
            instance.project, user,
            _('Item %(item)s status changed to %(status)s') % {'item': instance.item_id, 'status': instance.get_status_display()}
        )
        return

    old_priority = getattr(instance, '_old_priority', None)
    if old_priority and old_priority != instance.priority:
        AuditLog.objects.create(
            project=instance.project,
            user=user,
            action='priority_changed',
            target_type='Item',
            target_id=instance.item_id,
            details={'old_priority': old_priority, 'new_priority': instance.priority},
        )
        return

    AuditLog.objects.create(
        project=instance.project,
        user=user,
        action='updated',
        target_type='Item',
        target_id=instance.item_id,
    )


@receiver(post_delete, sender=Item)
def item_post_delete(sender, instance, **kwargs):
    _delete_file(instance.image)
    if _silent(instance) or _is_cascade_delete(instance, **kwargs):
        return
    user = _actor(instance, instance.created_by)
    AuditLog.objects.create(
        project=instance.project,
        user=user,
        action='deleted',
        target_type='Item',
        target_id=instance.item_id,
        details={'text': instance.text[:100]},
    )
    create_version(
        instance.project, user,
        _('Deleted item %(item)s') % {'item': instance.item_id}
    )


@receiver(post_delete, sender=Attachment)
def attachment_post_delete(sender, instance, **kwargs):
    _delete_file(instance.file)


@receiver(pre_save, sender=Section)
def section_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Section.objects.get(pk=instance.pk)
            instance._old_title = old.title
        except Section.DoesNotExist:
            instance._old_title = None
    else:
        instance._old_title = None


@receiver(post_save, sender=Section)
def section_post_save(sender, instance, created, **kwargs):
    if _silent(instance):
        return
    user = _actor(instance, instance.project.created_by)
    AuditLog.objects.create(
        project=instance.project,
        user=user,
        action='created' if created else 'updated',
        target_type='Section',
        target_id=instance.number,
        details={'title': instance.title},
    )


@receiver(post_delete, sender=Section)
def section_post_delete(sender, instance, **kwargs):
    if _silent(instance) or _is_cascade_delete(instance, **kwargs):
        return
    user = _actor(instance, instance.project.created_by)
    AuditLog.objects.create(
        project=instance.project,
        user=user,
        action='deleted',
        target_type='Section',
        target_id=instance.number,
        details={'title': instance.title},
    )


@receiver(pre_save, sender=ProjectMembership)
def membership_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = ProjectMembership.objects.get(pk=instance.pk)
            instance._old_role = old.role
        except ProjectMembership.DoesNotExist:
            instance._old_role = None
    else:
        instance._old_role = None


@receiver(post_save, sender=ProjectMembership)
def membership_post_save(sender, instance, created, **kwargs):
    user = _actor(instance, instance.added_by or instance.project.created_by)

    if created:
        AuditLog.objects.create(
            project=instance.project,
            user=user,
            action='collaborator_added',
            target_type='User',
            target_id=str(instance.user)[:50],
            details={
                'user_email': instance.user.email,
                'role': instance.role,
            },
        )
        if instance.user_id != user.pk:
            notification = Notification.objects.create(
                user=instance.user,
                actor=user,
                project=instance.project,
                type='collaborator_added',
                message=_('You were added to %(project)s as %(role)s') % {
                    'project': instance.project.name,
                    'role': instance.get_role_display(),
                },
                link=instance.project.get_absolute_url(),
            )
            push_notification(notification)
        _notify_project_users(
            instance.project, actor=user,
            notification_type='collaborator_added',
            message=_('%(user)s was added to %(project)s as %(role)s') % {
                'user': instance.user,
                'project': instance.project.name,
                'role': instance.get_role_display(),
            },
            exclude=(instance.user,),
        )
        return

    old_role = getattr(instance, '_old_role', None)
    if old_role and old_role != instance.role:
        AuditLog.objects.create(
            project=instance.project,
            user=user,
            action='collaborator_role_changed',
            target_type='User',
            target_id=str(instance.user)[:50],
            details={
                'user_email': instance.user.email,
                'old_role': old_role,
                'new_role': instance.role,
            },
        )
        notification = Notification.objects.create(
            user=instance.user,
            actor=user,
            project=instance.project,
            type='collaborator_added',
            message=_('Your role in %(project)s was changed to %(role)s') % {
                'project': instance.project.name,
                'role': instance.get_role_display(),
            },
            link=instance.project.get_absolute_url(),
        )
        push_notification(notification)


@receiver(post_delete, sender=ProjectMembership)
def membership_post_delete(sender, instance, **kwargs):
    if _is_cascade_delete(instance, **kwargs):
        return
    user = _actor(instance, instance.added_by or instance.project.created_by)
    AuditLog.objects.create(
        project=instance.project,
        user=user,
        action='collaborator_removed',
        target_type='User',
        target_id=str(instance.user)[:50],
        details={'user_email': instance.user.email, 'role': instance.role},
    )
    notification = Notification.objects.create(
        user=instance.user,
        actor=user,
        project=instance.project,
        type='collaborator_added',
        message=_('You were removed from %(project)s') % {'project': instance.project.name},
        link='/projects/',
    )
    push_notification(notification)


@receiver(post_save, sender=Comment)
def comment_post_save(sender, instance, created, **kwargs):
    if not created:
        return

    AuditLog.objects.create(
        project=instance.item.project,
        user=instance.author,
        action='commented',
        target_type='Item',
        target_id=instance.item.item_id,
        details={'text': instance.text[:100]},
    )

    recipients = set()
    if instance.item.created_by_id != instance.author_id:
        recipients.add(instance.item.created_by_id)
    if instance.parent and instance.parent.author_id != instance.author_id:
        recipients.add(instance.parent.author_id)

    for user_id in recipients:
        notification = Notification.objects.create(
            user_id=user_id,
            actor=instance.author,
            project=instance.item.project,
            type='comment',
            message=_('New comment on %(item)s in %(project)s') % {'item': instance.item.item_id, 'project': instance.item.project.name},
            link=instance.item.project.get_absolute_url(),
        )
        push_notification(notification)
