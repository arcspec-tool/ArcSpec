from contextlib import contextmanager

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.accounts.models import User
from apps.core.mixins import EDITOR_ROLES, project_with_role, visible_template
from apps.doctemplates.modals import sections_from_template
from apps.doctemplates.queries import template_list_queryset
from apps.mcp import identifiers, limits, output
from apps.mcp import text as markdown
from apps.mcp.errors import ToolRefusal, message_text, refusing
from apps.notifications.models import AuditLog
from apps.projects import writes
from apps.projects.models import Item, ItemAttributeValue, Project, ProjectMembership, Tag, TraceabilityLink
from apps.projects.queries import (
    attribute_rows,
    audit_log_queryset,
    global_search,
    item_detail_queryset,
    item_list_queryset,
    page_bounds,
    project_list_queryset,
    section_tree_with_counts,
    version_list_queryset,
)
from apps.projects.signals import create_version, notify_project_users


def load_user(user_key):
    try:
        return User.objects.get(public_key=user_key, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ToolRefusal(_('Not found: your account.'))


def member_project(user, slug):
    with refusing(_('project %(slug)s') % {'slug': slug}):
        return project_with_role(user, slug)


def editor_project(user, slug):
    with refusing(_('project %(slug)s') % {'slug': slug}):
        return project_with_role(user, slug, EDITOR_ROLES, writable=True)


def bounds(offset, limit, default, maximum):
    with refusing():
        return page_bounds(offset, limit, default, maximum)


def page(queryset, offset, limit):
    rows = list(queryset[offset:offset + limit + 1])
    return rows[:limit], len(rows) > limit


def roles_in(user, project_ids):
    if user.is_system_admin:
        return set(project_ids)
    return set(ProjectMembership.objects.filter(user=user, project_id__in=project_ids).values_list('project_id', flat=True))


def detail(user, found):
    tags = list(Tag.objects.filter(item_tags__item=found))
    linked = {link.target_item.project_id for link in found.outgoing_links.all()}
    linked |= {link.source_item.project_id for link in found.incoming_links.all()}
    return output.item_detail(found, tags, roles_in(user, linked), output.user_emails([found]))


def written_item(user, row, item):
    return detail(user, item_detail_queryset(row).get(pk=item.pk))


def project_item(row, value):
    return identifiers.item(Item.objects.filter(project=row), value)


@contextmanager
def field(name):
    try:
        yield
    except ToolRefusal as exc:
        raise ValidationError({name: str(exc)}) from None


def encoded_value(row, attribute, value):
    if value is None:
        return None
    if attribute.field_type == 'user':
        return str(identifiers.member(row, value).pk)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return ', '.join(str(part) for part in value)
    return str(value)


def attribute_values(row, attributes):
    values = {}
    for key, value in (attributes or {}).items():
        with field(key):
            attribute = identifiers.attribute(row, key)
            values[attribute.pk] = encoded_value(row, attribute, value)
    return values


def placement(row, section, changes, names=('before', 'after')):
    given = [name for name in names if changes.get(name)]
    if len(given) > 1:
        raise ValidationError({given[1]: _('Give only one of: %(names)s.') % {'names': ', '.join(names)}})
    position = {name: None for name in ('before', 'after')}
    if not given:
        return position
    name = given[0]
    if name == 'end':
        position['end'] = True
        return position
    with field(name):
        anchor = project_item(row, changes[name])
    if anchor.section_id != section.pk:
        raise ValidationError({name: _('The item is not in the chosen section.')})
    position[name] = anchor
    return position


def creation(row, entry):
    data = {'text': markdown.item_html(entry['text'])}
    with field('section'):
        data['section'] = identifiers.section(row, entry['section'])
    for name in ('status', 'priority'):
        if name in entry:
            data[name] = entry[name]
    if entry.get('assignee'):
        with field('assignee'):
            data['assignee'] = identifiers.member(row, entry['assignee'])
    with field('tags'):
        data['tags'] = list({tag.pk: tag for tag in (identifiers.tag(row, value) for value in entry.get('tags', ()))}.values())
    data['attribute_values'] = attribute_values(row, entry.get('attributes'))
    data.update(placement(row, data['section'], entry))
    return data


def item_ids(row, count):
    locked = Project.objects.select_for_update().get(pk=row.pk)
    first = locked.next_item_number
    allocated = []
    for offset in range(count):
        locked.next_item_number = first + offset
        allocated.append(locked.generate_item_id())
    Project.objects.filter(pk=row.pk).update(next_item_number=F('next_item_number') + count)
    return allocated


def anchor_groups(prepared):
    groups = {}
    for index, data in enumerate(prepared):
        anchor = data['before'] or data['after']
        kind = 'before' if data['before'] else 'after' if data['after'] else 'end'
        groups.setdefault((data['section'].pk, kind, anchor.pk if anchor else None), []).append(index)
    return groups.values()


def write_batch(row, user, prepared):
    allocated = item_ids(row, len(prepared))
    created = [None] * len(prepared)
    for indexes in anchor_groups(prepared):
        first = prepared[indexes[0]]
        anchor = first['before'] or first['after']
        if anchor is not None:
            anchor.refresh_from_db(fields=['order'])
        start = writes.place_item(row, first['section'], first['before'], first['after'], count=len(indexes))
        for offset, index in enumerate(indexes):
            data = prepared[index]
            fields = {name: data[name] for name in ('status', 'priority', 'assignee') if name in data}
            item = Item(
                project=row, section=data['section'], item_id=allocated[index], created_by=user,
                order=start + offset, text=data['text'], **fields,
            )
            item._silent = True
            item.save()
            created[index] = item
    ItemAttributeValue.objects.bulk_create([
        ItemAttributeValue(item=item, attribute=attribute, value=value)
        for item, data in zip(created, prepared)
        for attribute, value in data['attribute_values'].items() if value is not None
    ])
    for item, data in zip(created, prepared):
        if data['tags']:
            writes.replace_item_tags(row, item, data['tags'], user, record=False)
    entries = [
        AuditLog(project=row, user=user, action='created', target_type='Item', target_id=item.item_id,
                 details={'text': item.text[:100]})
        for item in created
    ]
    entries += [
        AuditLog(project=row, user=user, action='tag_added', target_type='Item', target_id=item.item_id,
                 details={'tags': sorted(tag.name for tag in data['tags'])})
        for item, data in zip(created, prepared) if data['tags']
    ]
    AuditLog.objects.bulk_create(entries)
    count = len(created)
    create_version(row, user, ngettext('Created %(count)d item', 'Created %(count)d items', count) % {'count': count})
    notify_project_users(
        row, actor=user, notification_type='item_created',
        message=ngettext(
            '%(count)d new item created in %(project)s', '%(count)d new items created in %(project)s', count,
        ) % {'count': count, 'project': row.name},
    )
    return created


def revision(row, item, changes):
    fields = {}
    if 'text' in changes:
        fields['text'] = markdown.item_html(changes['text'])
    if 'section' in changes:
        with field('section'):
            fields['section'] = identifiers.section(row, changes['section'])
    for name in ('status', 'priority'):
        if name in changes:
            fields[name] = changes[name]
    if 'assignee' in changes:
        fields['assignee'] = None
        if changes['assignee'] is not None:
            with field('assignee'):
                fields['assignee'] = identifiers.member(row, changes['assignee'])
    position = placement(row, fields.get('section', item.section), changes, ('before', 'after', 'end'))
    return fields, position, attribute_values(row, changes.get('attributes'))


def whoami(user_key):
    user = load_user(user_key)
    return {'name': str(user), 'email': user.email, 'system_role': user.system_role}


def list_projects(user_key, status=None, q='', offset=None, limit=None):
    user = load_user(user_key)
    offset, limit = bounds(offset, limit, 50, 100)
    rows, has_more = page(project_list_queryset(user, status or 'all', q), offset, limit)
    return {'projects': [output.project_row(row) for row in rows], 'has_more': has_more}


def get_project(user_key, project):
    user = load_user(user_key)
    row, role = member_project(user, project)
    memberships = row.memberships.select_related('user').order_by('added_at')
    return output.project_detail(row, role, memberships)


def list_sections(user_key, project):
    user = load_user(user_key)
    row, role = member_project(user, project)
    sections, root_sections, children_map = section_tree_with_counts(row)
    return {'sections': output.section_tree(root_sections, children_map)}


def list_items(user_key, project, section=None, status=None, priority=None, tag=None, assignee=None, text=None,
               offset=None, limit=None):
    user = load_user(user_key)
    row, role = member_project(user, project)
    offset, limit = bounds(offset, limit, 50, 100)
    queryset = item_list_queryset(
        row,
        status=status,
        priority=priority,
        tag=identifiers.tag(row, tag).name if tag else None,
        section=identifiers.section(row, section) if section else None,
        search=text,
        assignee=identifiers.assignee(row, assignee) if assignee else None,
    )
    items, has_more = page(queryset, offset, limit)
    emails = output.user_emails(items)
    return {'items': [output.item_row(item, emails) for item in items], 'has_more': has_more}


def get_item(user_key, project, item):
    user = load_user(user_key)
    row, role = member_project(user, project)
    return detail(user, identifiers.item(item_detail_queryset(row), item))


def list_tags(user_key, project):
    user = load_user(user_key)
    row, role = member_project(user, project)
    return {'tags': [output.tag_row(tag) for tag in Tag.for_project(row)]}


def list_attributes(user_key, project):
    user = load_user(user_key)
    row, role = member_project(user, project)
    return {'attributes': [output.attribute_fields(entry) for entry in attribute_rows(row)]}


def list_versions(user_key, project, offset=None, limit=None):
    user = load_user(user_key)
    row, role = member_project(user, project)
    offset, limit = bounds(offset, limit, 20, 50)
    versions, has_more = page(version_list_queryset(row), offset, limit)
    return {'versions': [output.version_row(version) for version in versions], 'has_more': has_more}


def list_audit_log(user_key, project, action=None, user=None, item=None, offset=None, limit=None):
    account = load_user(user_key)
    row, role = member_project(account, project)
    offset, limit = bounds(offset, limit, 50, 100)
    queryset = audit_log_queryset(
        row, action=action, user=identifiers.audit_user(row, user) if user else None, item_id=item,
    )
    entries, has_more = page(queryset, offset, limit)
    return {'entries': [output.audit_entry(entry) for entry in entries], 'has_more': has_more}


def list_templates(user_key, q='', doc_type=''):
    user = load_user(user_key)
    return {'templates': [output.template_row(template) for template in template_list_queryset(user, q, doc_type)]}


def get_template(user_key, template):
    user = load_user(user_key)
    try:
        row = visible_template(user, identifiers.as_key(template))
    except (Http404, PermissionDenied):
        raise ToolRefusal(_('Not found: template %(template)s.') % {'template': template}) from None
    return output.template_detail(row, sections_from_template(row), row.attributes.order_by('order'))


def search(user_key, q):
    user = load_user(user_key)
    projects, items = global_search(user, q)
    return output.search_result(projects, items)


def create_item(user_key, project, **entry):
    user = load_user(user_key)
    row, role = editor_project(user, project)
    with refusing():
        data = creation(row, entry)
    with limits.writing(), refusing():
        with transaction.atomic():
            item = writes.create_item(row, user, data)
    return written_item(user, row, item)


def create_items(user_key, project, items):
    user = load_user(user_key)
    row, role = editor_project(user, project)
    prepared = []
    for index, entry in enumerate(items):
        try:
            data = creation(row, entry)
            data['attribute_values'] = writes.checked_attribute_values(row, data['attribute_values'])
        except ValidationError as exc:
            raise ToolRefusal(message_text(exc, f'items[{index}].')) from None
        prepared.append(data)
    with limits.writing(), refusing():
        with transaction.atomic():
            created = write_batch(row, user, prepared)
    return {'items': [{'item_id': item.item_id, 'public_key': str(item.public_key)} for item in created]}


def update_item(user_key, project, item, **changes):
    user = load_user(user_key)
    row, role = editor_project(user, project)
    found = project_item(row, item)
    with refusing():
        fields, position, values = revision(row, found, changes)
    moved = any(position.values())
    with limits.writing(), refusing():
        with transaction.atomic():
            if fields or values:
                writes.update_item(row, found, user, {**fields, **position})
                if values:
                    writes.set_attribute_values(found, values, merge=True)
            elif moved:
                order = writes.place_item(row, found.section, position['before'], position['after'])
                Item.objects.filter(pk=found.pk).update(order=order)
    return written_item(user, row, found)


def set_item_tags(user_key, project, item, add=(), remove=()):
    user = load_user(user_key)
    row, role = editor_project(user, project)
    found = project_item(row, item)
    with refusing():
        with field('add'):
            added = [identifiers.tag(row, value) for value in add]
        with field('remove'):
            removed = {identifiers.tag(row, value).pk for value in remove}
    kept = {tag.pk: tag for tag in Tag.objects.filter(item_tags__item=found)}
    kept.update({tag.pk: tag for tag in added})
    with limits.writing(), refusing():
        with transaction.atomic():
            writes.replace_item_tags(row, found, [tag for pk, tag in kept.items() if pk not in removed], user)
    tags = Tag.objects.filter(item_tags__item=found)
    return {'tags': [{'public_key': str(tag.public_key), 'name': tag.name} for tag in tags]}


def add_comment(user_key, project, item, text, reply_to=None):
    user = load_user(user_key)
    row, role = editor_project(user, project)
    found = project_item(row, item)
    parent = identifiers.comment(found, reply_to) if reply_to else None
    with refusing():
        if not text.strip():
            raise ValidationError({'text': _('Enter the comment text.')})
    with limits.writing(), refusing():
        with transaction.atomic():
            comment = writes.create_comment(found, user, text.strip(), parent)
    return {'public_key': str(comment.public_key), 'created_at': output.stamp(comment.created_at)}


def add_link(user_key, project, item, target_item, type, target_project=None):
    user = load_user(user_key)
    row, role = editor_project(user, project)
    source = project_item(row, item)
    other = row if target_project in (None, row.slug) else member_project(user, target_project)[0]
    target = identifiers.item(Item.objects.filter(project=other).select_related('project'), target_item)
    with refusing():
        if TraceabilityLink.objects.filter(source_item=source, target_item=target, link_type=type).exists():
            raise ValidationError({'target_item': _('This link already exists.')})
    with limits.writing(), refusing():
        with transaction.atomic():
            link = writes.create_link(row, user, source, target, type)
    return {'public_key': str(link.public_key)}
