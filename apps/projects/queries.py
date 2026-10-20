from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from apps.notifications.models import AuditLog
from apps.projects.models import Item, Project, ProjectMembership, ProjectVersion

SORT_OPTIONS = {
    'updated': '-updated_at',
    'name-asc': 'name',
    'name-desc': '-name',
    'created': '-created_at',
}

AUDIT_ACTION_GROUPS = {
    'collaboration': ('collaborator_added', 'collaborator_removed', 'collaborator_role_changed'),
}


def count_per_project(queryset):
    counted = queryset.filter(project=OuterRef('pk')).order_by().values('project').annotate(n=Count('pk')).values('n')[:1]
    return Coalesce(Subquery(counted), 0)


def project_list_queryset(user, status='all', q='', sort='updated'):
    qs = Project.objects.for_user(user).select_related('template')
    if status and status != 'all':
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if user.is_system_admin:
        role = Value('admin')
    else:
        role = Subquery(ProjectMembership.objects.filter(project=OuterRef('pk'), user=user).values('role')[:1])
    qs = qs.annotate(
        items_total=count_per_project(Item.objects.all()),
        members_total=count_per_project(ProjectMembership.objects.all()),
        user_role=role,
        is_archived=models.Case(
            models.When(status='archived', then=models.Value(1)),
            default=models.Value(0),
            output_field=models.IntegerField(),
        ),
    )
    return qs.order_by('is_archived', SORT_OPTIONS[sort])


def section_tree_with_counts(project):
    sections = list(project.sections.select_related('parent').order_by('order'))
    own_counts = dict(
        Item.objects.filter(project=project).order_by().values_list('section_id').annotate(n=Count('pk'))
    )
    root_sections = []
    children_map = {}
    for section in sections:
        section.own_items = own_counts.get(section.pk, 0)
        if section.parent_id is None:
            root_sections.append(section)
        else:
            children_map.setdefault(section.parent_id, []).append(section)

    def count_items(section):
        section.total_items = section.own_items + sum(
            count_items(child) for child in children_map.get(section.pk, [])
        )
        return section.total_items

    for section in root_sections:
        count_items(section)
    return sections, root_sections, children_map


def attribute_row(attribute):
    return {
        'id': attribute.pk,
        'public_key': str(attribute.public_key),
        'name': attribute.name,
        'field_type': attribute.field_type,
        'options': attribute.options,
        'is_builtin': attribute.is_builtin,
        'order': attribute.order,
    }


def attribute_rows(project):
    return [attribute_row(attribute) for attribute in project.attributes.order_by('order')]


def item_list_queryset(project, status=None, priority=None, tag=None, section=None, search=None, assignee=None):
    qs = Item.objects.filter(project=project).select_related(
        'section', 'assignee'
    ).prefetch_related(
        'item_tags__tag', 'attribute_values__attribute'
    ).order_by('section__order', 'order')
    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    if tag:
        qs = qs.filter(item_tags__tag__name=tag)
    if section:
        qs = qs.filter(section=section)
    if search and len(search) >= 2:
        qs = qs.filter(Q(item_id__icontains=search) | Q(text__icontains=search))
    if assignee:
        qs = qs.filter(assignee=assignee)
    return qs.distinct()


def item_detail_queryset(project):
    return Item.objects.filter(project=project).select_related(
        'section', 'assignee', 'created_by'
    ).prefetch_related(
        'attribute_values__attribute', 'attachments__uploaded_by', 'comments__author',
        'outgoing_links__target_item__project', 'outgoing_links__source_item__project',
        'incoming_links__source_item__project', 'incoming_links__target_item__project',
    )


def audit_log_queryset(project, action=None, user=None, item_id=None):
    qs = AuditLog.objects.filter(project=project).select_related('user')
    if action in AUDIT_ACTION_GROUPS:
        qs = qs.filter(action__in=AUDIT_ACTION_GROUPS[action])
    elif action and action != 'all':
        qs = qs.filter(action=action)
    if user:
        qs = qs.filter(user=user)
    if item_id:
        qs = qs.filter(target_type='Item', target_id=item_id)
    return qs


def audit_row(entry):
    return {
        'id': entry.pk,
        'action': entry.action,
        'action_display': entry.get_action_display(),
        'target_type': entry.target_type,
        'target_id': entry.target_id,
        'user_name': str(entry.user),
        'details': entry.details,
        'created_at': entry.created_at.isoformat(),
    }


def _page_number(value, name, default):
    if value is None or value == '':
        return default
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValidationError({name: _('%(name)s must be a whole number of 0 or more.') % {'name': name}})
    return int(value)


def page_bounds(offset, limit, default, maximum):
    offset = _page_number(offset, 'offset', 0)
    limit = _page_number(limit, 'limit', default)
    return offset, min(limit, maximum)


def global_search(user, q):
    user_projects = Project.objects.for_user(user)
    projects = user_projects.filter(Q(name__icontains=q) | Q(description__icontains=q))[:5]
    items = Item.objects.filter(project__in=user_projects).filter(
        Q(item_id__icontains=q) | Q(text__icontains=q)
    ).select_related('project', 'section')[:10]
    return projects, items


def version_list_queryset(project):
    return ProjectVersion.objects.filter(project=project).select_related('changed_by').defer('snapshot')
