import json

from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.doctemplates.models import Template
from apps.doctemplates.queries import sections_from_template
from apps.doctemplates.writes import OPTION_TYPES, attribute_rows, section_rows

FORMAT = 'arcspec-template'
VERSION = 1
REQUIRED_FIELDS = {'format', 'version', 'name', 'doc_type'}
FIELDS = REQUIRED_FIELDS | {'description', 'sections', 'attributes'}


def section_entries(nodes):
    return [
        {'title': node['title'], 'description': node['description'], 'children': section_entries(node['children'])}
        for node in nodes
    ]


def attribute_entry(attribute):
    entry = {'name': attribute.name, 'type': attribute.field_type}
    if attribute.field_type in OPTION_TYPES:
        entry['options'] = list(attribute.options or [])
    return entry


def template_file(template):
    return {
        'format': FORMAT,
        'version': VERSION,
        'name': template.name,
        'description': template.description,
        'doc_type': template.doc_type,
        'sections': section_entries(sections_from_template(template)),
        'attributes': [attribute_entry(attribute) for attribute in template.attributes.order_by('order')],
    }


def file_content(template):
    return json.dumps(template_file(template), ensure_ascii=False, indent=2) + '\n'


def file_name(template):
    return f'{slugify(template.name) or "template"}.json'


def refuse_constant(name):
    raise ValueError(name)


def unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValidationError(_('The file has the key "%(key)s" twice.') % {'key': key})
        data[key] = value
    return data


def holds_nul(data):
    stack = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, str) and '\x00' in value:
            return True
        if isinstance(value, dict):
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False


def read_file(content):
    try:
        data = json.loads(content.decode('utf-8-sig'), parse_constant=refuse_constant, object_pairs_hook=unique_keys)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValidationError(_('The file is not valid JSON.')) from None
    if holds_nul(data):
        raise ValidationError(_('The file holds a NUL character.'))
    if not isinstance(data, dict) or data.get('format') != FORMAT or type(data.get('version')) is not int:
        raise ValidationError(_('The file is not an ArcSpec template file.'))
    if data['version'] != VERSION:
        raise ValidationError(_('Version %(version)d of the template file format is not supported.') % {
            'version': data['version'],
        })
    if (
        not REQUIRED_FIELDS <= data.keys() <= FIELDS
        or not all(isinstance(data.get(field, ''), str) for field in ('name', 'description', 'doc_type'))
        or not all(isinstance(data.get(field, []), list) for field in ('sections', 'attributes'))
    ):
        raise ValidationError(_(
            'A template file must have a name and a doc_type, and can have a description, sections and attributes.'
        ))
    return data


def template_from_file(content, user):
    data = read_file(content)
    name = data['name'].strip()
    longest = Template._meta.get_field('name').max_length
    if not name:
        raise ValidationError(_('The template in the file has no name.'))
    if len(name) > longest:
        raise ValidationError(_('The template name is longer than %(count)d characters.') % {'count': longest})
    types = dict(Template.DOC_TYPE_CHOICES)
    if data['doc_type'] not in types:
        raise ValidationError(_('The doc_type %(type)s is not one of: %(types)s.') % {
            'type': data['doc_type'], 'types': ', '.join(types),
        })
    template = Template(
        name=name, description=data.get('description', '').strip(), doc_type=data['doc_type'],
        is_builtin=False, is_global=False, created_by=user,
    )
    template.full_clean()
    return template, section_rows(data.get('sections', [])), attribute_rows(template, data.get('attributes', []))
