import datetime

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.notifications.models import AuditLog
from apps.projects.models import (
    Attachment,
    Comment,
    Item,
    ItemAttributeValue,
    ItemTag,
    Project,
    ProjectMembership,
    Tag,
    TraceabilityLink,
)
from apps.projects.signals import record_item_created

ITEM_FIELDS = ('text', 'status', 'priority', 'assignee', 'image', 'image_caption')


def section_in_project(project, section):
    if section is None or section.project_id != project.pk:
        raise ValidationError({'section': _('Section does not belong to this project.')})
    return section


def assignable(project, user):
    if user is None or user == '':
        return None
    if not isinstance(user, User):
        try:
            user = User.objects.get(pk=user)
        except (User.DoesNotExist, ValueError, TypeError):
            raise ValidationError({'assignee': _('Assignee user not found or inactive.')})
    if not user.is_active:
        raise ValidationError({'assignee': _('Assignee user not found or inactive.')})
    if not user.is_system_admin and not ProjectMembership.objects.filter(project=project, user=user).exists():
        raise ValidationError({'assignee': _('Assignee must be a project member.')})
    return user


def _choice(field, value, choices):
    if value not in dict(choices):
        raise ValidationError({field: _('Invalid %(field)s. Must be one of: %(choices)s') % {
            'field': field, 'choices': [key for key, label in choices],
        }})
    return value


def place_item(project, section, before=None, after=None, count=1):
    anchor = before or after
    if anchor is not None:
        if anchor.section_id != section.pk:
            raise ValidationError({'before' if before else 'after': _('The item is not in the chosen section.')})
        order = anchor.order if before else anchor.order + 1
        Item.objects.filter(project=project, section=section, order__gte=order).update(order=F('order') + count)
        return order
    max_order = Item.objects.filter(project=project, section=section).aggregate(m=models.Max('order'))['m']
    return (max_order or 0) + 1


def _checked_value(attribute, value):
    if value is None or value == '':
        return None
    value = str(value)
    field_type = attribute.field_type
    if field_type == 'number':
        try:
            float(value)
        except ValueError:
            raise ValidationError({attribute.name: _('Enter a number.')})
    elif field_type == 'date':
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            raise ValidationError({attribute.name: _('Enter a date as YYYY-MM-DD.')})
    elif field_type == 'boolean':
        if value not in ('true', 'false'):
            raise ValidationError({attribute.name: _('Enter true or false.')})
    elif field_type == 'user':
        if not value.isdigit() or not User.objects.filter(pk=int(value), is_active=True).exists():
            raise ValidationError({attribute.name: _('Assignee user not found or inactive.')})
    elif field_type == 'dropdown':
        if value not in attribute.options:
            raise ValidationError({attribute.name: _('Choose one of: %(options)s') % {'options': ', '.join(attribute.options)}})
    elif field_type == 'multiselect':
        parts = [part.strip() for part in value.split(',') if part.strip()]
        unknown = [part for part in parts if part not in attribute.options]
        if unknown:
            raise ValidationError({attribute.name: _('Choose from: %(options)s') % {'options': ', '.join(attribute.options)}})
        value = ', '.join(parts)
    return value


def checked_attribute_values(project, values):
    attributes = {attribute.pk: attribute for attribute in project.attributes.all()}
    checked = {}
    for key, value in (values or {}).items():
        attribute = attributes.get(key) if isinstance(key, int) and not isinstance(key, bool) else None
        if attribute is None:
            raise ValidationError({'attribute_values': _('Attribute %(id)s is not available for this project.') % {'id': key}})
        if attribute.is_builtin:
            raise ValidationError({attribute.name: _('Built-in attributes cannot be set.')})
        checked[attribute] = _checked_value(attribute, value)
    return checked


def set_attribute_values(item, values, merge=False):
    checked = checked_attribute_values(item.project, values)
    with transaction.atomic():
        if merge:
            item.attribute_values.filter(attribute__in=checked).delete()
        else:
            item.attribute_values.all().delete()
        ItemAttributeValue.objects.bulk_create([
            ItemAttributeValue(item=item, attribute=attribute, value=value)
            for attribute, value in checked.items() if value is not None
        ])


def replace_item_tags(project, item, tags, user, record=True):
    available = {tag.pk: tag for tag in Tag.for_project(project)}
    chosen = {}
    for tag in tags or ():
        key = tag.pk if isinstance(tag, Tag) else tag
        if key not in available:
            raise ValidationError({'tag_ids': _('Tag %(tag)s is not available for this project.') % {'tag': key}})
        chosen[key] = available[key]
    with transaction.atomic():
        old_names = set(Tag.objects.filter(item_tags__item=item).values_list('name', flat=True))
        ItemTag.objects.filter(item=item).delete()
        ItemTag.objects.bulk_create([ItemTag(item=item, tag=tag) for tag in chosen.values()])
        new_names = {tag.name for tag in chosen.values()}
        if record:
            for action, names in (('tag_added', new_names - old_names), ('tag_removed', old_names - new_names)):
                if names:
                    AuditLog.objects.create(
                        project=project, user=user, action=action,
                        target_type='Item', target_id=item.item_id,
                        details={'tags': sorted(names)},
                    )
    return Tag.objects.filter(item_tags__item=item)


def create_item(project, user, data):
    section = section_in_project(project, data.get('section'))
    fields = {field: data[field] for field in ITEM_FIELDS if field in data}
    fields['status'] = _choice('status', fields.get('status', 'draft'), Item.STATUS_CHOICES)
    fields['priority'] = _choice('priority', fields.get('priority', 'medium'), Item.PRIORITY_CHOICES)
    fields['assignee'] = assignable(project, fields.get('assignee'))
    tags = list(data.get('tags') or ())
    with transaction.atomic():
        locked_project = Project.objects.select_for_update().get(pk=project.pk)
        item_id = locked_project.generate_item_id()
        Project.objects.filter(pk=project.pk).update(next_item_number=F('next_item_number') + 1)
        order = place_item(project, section, data.get('before'), data.get('after'))
        item = Item(project=project, section=section, item_id=item_id, created_by=user, order=order, **fields)
        item._silent = True
        item.save()
        set_attribute_values(item, data.get('attribute_values'))
        tag_rows = replace_item_tags(project, item, tags, user, record=False)
        record_item_created(item, user)
        if tags:
            AuditLog.objects.create(
                project=project, user=user, action='tag_added',
                target_type='Item', target_id=item.item_id,
                details={'tags': sorted(tag_rows.values_list('name', flat=True))},
            )
    item._silent = False
    item._actor = user
    return item


def update_item(project, item, user, changes):
    fields = {field: changes[field] for field in ('section',) + ITEM_FIELDS if field in changes}
    if 'section' in fields:
        fields['section'] = section_in_project(project, fields['section'])
    if 'status' in fields:
        _choice('status', fields['status'], Item.STATUS_CHOICES)
    if 'priority' in fields:
        _choice('priority', fields['priority'], Item.PRIORITY_CHOICES)
    if 'assignee' in fields:
        fields['assignee'] = assignable(project, fields['assignee'])
    before, after, end = changes.get('before'), changes.get('after'), changes.get('end')
    with transaction.atomic():
        for field, value in fields.items():
            setattr(item, field, value)
        item._actor = user
        item.save()
        if before is not None or after is not None or end:
            order = place_item(project, item.section, before, after)
            Item.objects.filter(pk=item.pk).update(order=order)
            item.order = order
    return item


def create_comment(item, user, text, parent=None):
    if parent is not None and parent.item_id != item.pk:
        raise ValidationError({'parent': _('The parent comment is on another item.')})
    return Comment.objects.create(item=item, author=user, text=text, parent=parent)


def create_link(project, user, source, target, link_type):
    if source.project_id != project.pk:
        raise ValidationError({'source_item': _('Source item must belong to the current project.')})
    if target.pk == source.pk:
        raise ValidationError({'target_item': _('An item cannot link to itself.')})
    if not target.project.get_user_role(user):
        raise ValidationError({'target_item': _("You do not have access to the target item's project.")})
    if target.project.status == 'archived':
        raise ValidationError({'target_item': _('The target project is archived.')})
    _choice('link_type', link_type, TraceabilityLink.LINK_TYPE_CHOICES)
    with transaction.atomic():
        link = TraceabilityLink.objects.create(source_item=source, target_item=target, link_type=link_type, created_by=user)
        AuditLog.objects.create(
            project=source.project, user=user, action='link_added',
            target_type='Item', target_id=source.item_id,
            details={'link_type': link_type, 'target': target.item_id},
        )
    return link


def set_item_image(item, user, uploaded, caption=''):
    had_image = bool(item.image)
    old_filename = item.image.name if item.image else None
    if item.image:
        item.image.delete(save=False)

    item.image = uploaded
    if caption:
        item.image_caption = caption
    item._actor = user
    item.save()

    audit_details = {
        'field': 'image',
        'action': 'changed' if had_image else 'added',
        'filename': uploaded.name,
    }
    if had_image:
        audit_details['previous_filename'] = old_filename.split('/')[-1] if old_filename else None
    AuditLog.objects.create(
        project=item.project, user=user, action='edited',
        target_type='Item', target_id=item.item_id,
        details=audit_details,
    )
    return item


def remove_item_image(item, user):
    if item.image:
        item.image.delete(save=False)
    item.image = None
    item.image_caption = ''
    item._actor = user
    item.save()

    AuditLog.objects.create(
        project=item.project, user=user, action='edited',
        target_type='Item', target_id=item.item_id,
        details={'field': 'image', 'action': 'removed'},
    )
    return item


def add_attachment(item, user, uploaded):
    attachment = Attachment.objects.create(
        item=item,
        file=uploaded,
        uploaded_by=user,
        filename=uploaded.name,
        file_size=uploaded.size,
    )
    AuditLog.objects.create(
        project=item.project, user=user, action='attachment_added',
        target_type='Item', target_id=item.item_id,
        details={'filename': uploaded.name},
    )
    return attachment


def remove_attachment(attachment, user):
    item = attachment.item
    filename = attachment.filename
    attachment.delete()
    AuditLog.objects.create(
        project=item.project, user=user, action='attachment_removed',
        target_type='Item', target_id=item.item_id,
        details={'filename': filename},
    )
