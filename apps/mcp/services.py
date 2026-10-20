from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.core.mixins import project_with_role, visible_template
from apps.doctemplates.modals import sections_from_template
from apps.doctemplates.queries import template_list_queryset
from apps.mcp import identifiers, output
from apps.mcp.errors import ToolRefusal, refusing
from apps.projects.models import ProjectMembership, Tag
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


def load_user(user_key):
    try:
        return User.objects.get(public_key=user_key, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ToolRefusal(_('Not found: your account.'))


def member_project(user, slug):
    with refusing(_('project %(slug)s') % {'slug': slug}):
        return project_with_role(user, slug)


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
    found = identifiers.item(item_detail_queryset(row), item)
    tags = list(Tag.objects.filter(item_tags__item=found))
    linked = {link.target_item.project_id for link in found.outgoing_links.all()}
    linked |= {link.source_item.project_id for link in found.incoming_links.all()}
    return output.item_detail(found, tags, roles_in(user, linked), output.user_emails([found]))


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
