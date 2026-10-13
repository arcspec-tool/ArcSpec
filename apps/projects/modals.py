from django.shortcuts import get_object_or_404
from django.urls import reverse

from apps.accounts.models import UserSettings
from apps.core.mixins import ADMIN_ROLES, EDITOR_ROLES, MEMBER_ROLES, project_with_role, require_not_viewer
from apps.core.modals import key_param, register, slug_param
from apps.projects.forms import ProjectForm, ProjectUpdateForm
from apps.projects.models import Item, ProjectAttribute, ProjectMembership, TraceabilityLink

COLORS = ('#284E8A', '#7c3aed', '#198754', '#ea580c', '#0dcaf0', '#dc3545')
DEFAULT_COLOR = COLORS[0]
EXPORT_FORMATS = ('pdf', 'docx')
OPTION_TYPES = ('dropdown', 'multiselect')


def selected_color(form, fallback):
    value = form.data.get('color') if form.is_bound else fallback
    return value if value in COLORS else fallback


def project_create_context(request, form=None):
    form = form or ProjectForm(user=request.user)
    return {
        'form': form,
        'form_action': reverse('project_create'),
        'colors': COLORS,
        'selected_color': selected_color(form, DEFAULT_COLOR),
    }


def project_edit_context(project, form=None):
    form = form or ProjectUpdateForm(instance=project)
    return {
        'project': project,
        'form': form,
        'form_action': reverse('project_update', args=[project.slug]),
        'colors': COLORS,
        'selected_color': selected_color(form, project.color),
    }


def project_param(request, params, roles, writable=False):
    return project_with_role(request.user, slug_param(params, 'project'), roles, writable)


def item_param(project, params):
    return get_object_or_404(Item, project=project, public_key=key_param(params, 'item'))


def attribute_fields(project, memberships, values):
    fields = []
    for attribute in project.attributes.filter(is_builtin=False).order_by('order'):
        value = values.get(attribute.pk, '')
        fields.append({
            'attribute': attribute,
            'value': value,
            'selected': [part.strip() for part in value.split(',')] if value and attribute.field_type == 'multiselect' else [],
            'users': memberships if attribute.field_type == 'user' else (),
        })
    return fields


def item_form_context(project, values=None):
    memberships = ProjectMembership.objects.filter(project=project).select_related('user').order_by('user__first_name', 'user__last_name')
    return {
        'project': project,
        'sections': project.sections.order_by('order'),
        'memberships': memberships,
        'attribute_fields': attribute_fields(project, memberships, values or {}),
        'status_choices': Item.STATUS_CHOICES,
        'priority_choices': Item.PRIORITY_CHOICES,
    }


def section_node(section):
    return {
        'id': section.pk,
        'key': str(section.public_key),
        'number': section.number,
        'title': section.title,
        'description': section.description,
        'children': [],
    }


def section_tree(project):
    sections = list(project.sections.order_by('order'))
    nodes = {s.pk: section_node(s) for s in sections}
    roots = []
    for s in sections:
        parent = nodes.get(s.parent_id) if s.parent_id else None
        (parent['children'] if parent else roots).append(nodes[s.pk])
    return roots


def attribute_row(attribute):
    return {
        'id': attribute.pk,
        'key': str(attribute.public_key),
        'name': attribute.name,
        'field_type': attribute.field_type,
        'options_text': ', '.join(attribute.options or []),
    }


@register('project_create', 'projects/modals/_project_create.html', modal_id='newProjectModal', size='lg')
def project_create(request, params):
    require_not_viewer(request.user)
    return project_create_context(request)


@register('project_edit', 'projects/modals/_project_edit.html', params=('project',), modal_id='editProjectModal', size='lg')
def project_edit(request, params):
    project, _ = project_param(request, params, ADMIN_ROLES, writable=True)
    return project_edit_context(project)


@register('project_delete', 'projects/modals/_project_delete.html', params=('project',), modal_id='deleteProjectModal')
def project_delete(request, params):
    project, _ = project_param(request, params, ADMIN_ROLES)
    return {'project': project, 'form_action': reverse('project_delete', args=[project.slug])}


@register('add_item', 'projects/modals/_add_item.html', params=('project', 'section'), modal_id='addItemModal', size='lg')
def add_item(request, params):
    project, _ = project_param(request, params, EDITOR_ROLES, writable=True)
    context = item_form_context(project)
    context['selected_section'] = None
    if params.get('section'):
        section = get_object_or_404(project.sections, public_key=key_param(params, 'section'))
        context['selected_section'] = section.pk
    return context


@register('edit_item', 'projects/modals/_edit_item.html', params=('project', 'item'), modal_id='editItemModal', size='lg')
def edit_item(request, params):
    project, _ = project_param(request, params, EDITOR_ROLES, writable=True)
    item = item_param(project, params)
    values = {value.attribute_id: value.value for value in item.attribute_values.all()}
    context = item_form_context(project, values)
    context.update({
        'item': item,
        'selected_section': item.section_id,
        'image_url': reverse('item_image', args=[project.slug, item.public_key]) if item.image else '',
    })
    return context


@register('delete_item', 'projects/modals/_delete_item.html', params=('project', 'item'), modal_id='deleteItemModal', size='sm')
def delete_item(request, params):
    project, _ = project_param(request, params, EDITOR_ROLES, writable=True)
    return {'project': project, 'item': item_param(project, params)}


@register('collaborators', 'projects/modals/_collaborators.html', params=('project',), modal_id='collaboratorsModal', size='lg')
def collaborators(request, params):
    project, role = project_param(request, params, MEMBER_ROLES)
    return {
        'project': project,
        'is_admin': role == 'admin' and project.status != 'archived',
        'memberships': ProjectMembership.objects.filter(project=project).select_related('user').order_by('user__first_name', 'user__last_name'),
        'role_choices': ProjectMembership.ROLE_CHOICES,
    }


@register('export', 'projects/modals/_export.html', params=('project', 'format'), modal_id='exportModal')
def export(request, params):
    project, _ = project_param(request, params, MEMBER_ROLES)
    export_format = params.get('format') if params.get('format') in EXPORT_FORMATS else 'pdf'
    try:
        defaults = request.user.settings
    except UserSettings.DoesNotExist:
        defaults = UserSettings()
    return {
        'project': project,
        'export_format': export_format,
        'defaults': defaults,
        'attributes': project.attributes.filter(is_builtin=False).order_by('order'),
        'form_action': reverse('project_export', args=[project.slug]),
    }


@register('save_view', 'projects/modals/_save_view.html', params=('project',), modal_id='saveViewModal', size='sm')
def save_view(request, params):
    project, _ = project_param(request, params, MEMBER_ROLES)
    return {'project': project}


@register('add_link', 'projects/modals/_add_link.html', params=('project',), modal_id='addLinkModal')
def add_link(request, params):
    project, _ = project_param(request, params, EDITOR_ROLES, writable=True)
    return {'project': project, 'link_type_choices': TraceabilityLink.LINK_TYPE_CHOICES}


@register('manage_sections', 'projects/modals/_manage_sections.html', params=('project',), modal_id='manageSectionsModal', size='lg', scrollable=True)
def manage_sections(request, params):
    project, _ = project_param(request, params, EDITOR_ROLES, writable=True)
    return {
        'project': project,
        'sections': section_tree(project),
        'attributes': [attribute_row(a) for a in project.attributes.filter(is_builtin=False).order_by('order')],
        'field_types': ProjectAttribute.FIELD_TYPE_CHOICES,
        'blank_section': {'id': '', 'key': '', 'number': '', 'title': '', 'description': '', 'children': []},
        'blank_attribute': {'id': '', 'key': '', 'name': '', 'field_type': 'text', 'options_text': ''},
    }
