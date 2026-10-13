from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.mixins import editable_template, require_not_viewer, visible_template
from apps.core.modals import key_param, register
from apps.doctemplates.forms import TemplateForm, TemplateSectionFormSet
from apps.doctemplates.models import TemplateAttribute

MAX_POSTED_SECTIONS = 1000
OPTION_TYPES = ('dropdown', 'multiselect')


def section_node(section_id, number, title, description):
    return {'id': section_id, 'number': number, 'title': title, 'description': description, 'children': []}


def sections_from_template(template):
    sections = list(template.sections.order_by('order'))
    nodes = {s.pk: section_node(s.pk, s.number, s.title, s.description) for s in sections}
    roots = []
    for s in sections:
        parent = nodes.get(s.parent_id) if s.parent_id else None
        (parent['children'] if parent else roots).append(nodes[s.pk])
    return roots


def sections_from_post(post):
    try:
        total = min(int(post.get('sections-TOTAL_FORMS', 0) or 0), MAX_POSTED_SECTIONS)
    except ValueError:
        total = 0
    nodes = {}
    order = []
    for i in range(total):
        ref = post.get(f'sections-{i}-ref', '') or f'ref-{i}'
        node = section_node(
            post.get(f'sections-{i}-id', ''),
            post.get(f'sections-{i}-number', ''),
            post.get(f'sections-{i}-title', ''),
            post.get(f'sections-{i}-description', ''),
        )
        nodes[ref] = (node, post.get(f'sections-{i}-parent_ref', ''))
        order.append(ref)
    roots = []
    for ref in order:
        node, parent_ref = nodes[ref]
        parent = nodes.get(parent_ref) if parent_ref else None
        (parent[0]['children'] if parent else roots).append(node)
    return roots


def attribute_row(name, field_type, options):
    if field_type not in dict(TemplateAttribute.FIELD_TYPE_CHOICES):
        field_type = 'text'
    return {'name': name, 'field_type': field_type, 'options_text': ', '.join(options)}


def attributes_from_template(template):
    return [
        attribute_row(attr.name, attr.field_type, attr.options or [])
        for attr in template.attributes.filter(is_builtin=False).order_by('order')
    ]


def attributes_from_post(post):
    names = post.getlist('attr_name[]')
    types = post.getlist('attr_type[]')
    options = post.getlist('attr_options[]')
    rows = []
    for i, name in enumerate(names):
        field_type = types[i] if i < len(types) else 'text'
        option_list = [o.strip() for o in options[i].split(',') if o.strip()] if i < len(options) else []
        rows.append(attribute_row(name, field_type, option_list))
    return rows


def editor_context(template=None, form=None, sections=None, attributes=None):
    if template is not None:
        form = form or TemplateForm(instance=template)
        action = reverse('template_edit', args=[template.public_key])
        title = _('Edit Template')
        sections = sections_from_template(template) if sections is None else sections
        attributes = attributes_from_template(template) if attributes is None else attributes
    else:
        form = form or TemplateForm()
        action = reverse('template_create')
        title = _('Create Template')
        sections = sections or []
        attributes = attributes or []
    return {
        'template': template,
        'template_form': form,
        'form_action': action,
        'editor_title': title,
        'sections': sections,
        'attributes': attributes,
        'section_formset': TemplateSectionFormSet(prefix='sections'),
        'field_types': TemplateAttribute.FIELD_TYPE_CHOICES,
        'blank_section': section_node('', '', '', ''),
        'blank_attribute': attribute_row('', 'text', []),
    }


@register('template_editor', 'doctemplates/modals/_template_editor.html', params=('template',), modal_id='templateEditorModal', size='xl', scrollable=True)
def template_editor(request, params):
    if 'template' in params:
        template = editable_template(request.user, key_param(params, 'template'))
        return editor_context(template)
    require_not_viewer(request.user)
    return editor_context()


@register('template_view', 'doctemplates/modals/_view_template.html', params=('template',), modal_id='viewTemplateModal', size='lg', scrollable=True)
def template_view(request, params):
    template = visible_template(request.user, key_param(params, 'template'))
    return {
        'template': template,
        'sections': sections_from_template(template),
        'attributes': template.attributes.order_by('order'),
        'can_duplicate': not request.user.is_viewer,
    }
