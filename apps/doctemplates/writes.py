from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.doctemplates.models import TemplateAttribute, TemplateSection

MAX_POSTED_SECTIONS = 1000
OPTION_TYPES = ('dropdown', 'multiselect')
SECTION_FIELDS = {'title', 'description', 'children'}
ATTRIBUTE_FIELDS = {'name', 'type', 'options'}


def duplicate_attribute_names(template, names):
    names = list(names)
    if template is not None and template.pk:
        names += template.attributes.filter(is_builtin=True).values_list('name', flat=True)
    return sorted({name for name in names if names.count(name) > 1})


def section_shape_error(number):
    return ValidationError({'sections': _(
        'Section %(number)s must be an object with a title, and can have a description and children.'
    ) % {'number': number}})


def section_rows(entries):
    longest = TemplateSection._meta.get_field('number').max_length
    longest_title = TemplateSection._meta.get_field('title').max_length
    rows = []

    def add(level, parent):
        for position, entry in enumerate(level, start=1):
            number = f'{parent}.{position}' if parent else str(position)
            if len(number) > longest:
                raise ValidationError({'sections': _(
                    'The section tree is too deep: section number %(number)s is longer than %(count)d characters.'
                ) % {'number': number, 'count': longest}})
            if (
                not isinstance(entry, dict) or not entry.keys() <= SECTION_FIELDS
                or not isinstance(entry.get('title'), str) or not isinstance(entry.get('description', ''), str)
                or not isinstance(entry.get('children', []), list)
            ):
                raise section_shape_error(number)
            title = entry['title'].strip()
            if not title:
                raise ValidationError({'sections': _('Section %(number)s has no title.') % {'number': number}})
            if len(title) > longest_title:
                raise ValidationError({'sections': _(
                    'The title of section %(number)s is longer than %(count)d characters.'
                ) % {'number': number, 'count': longest_title}})
            rows.append({
                'title': title, 'description': entry.get('description', '').strip(), 'number': number,
                'order': len(rows), 'ref': number, 'parent_ref': parent or None,
            })
            add(entry.get('children', ()), number)

    add(entries, '')
    if len(rows) > MAX_POSTED_SECTIONS:
        raise ValidationError({'sections': _('A template holds at most %(count)d sections.') % {'count': MAX_POSTED_SECTIONS}})
    return rows


def attribute_rows(template, entries):
    longest = TemplateAttribute._meta.get_field('name').max_length
    types = dict(TemplateAttribute.FIELD_TYPE_CHOICES)
    rows = []
    for position, entry in enumerate(entries, start=1):
        options = entry.get('options', []) if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict) or not entry.keys() <= ATTRIBUTE_FIELDS
            or not isinstance(entry.get('name'), str) or not isinstance(entry.get('type'), str)
            or not isinstance(options, list) or not all(isinstance(option, str) for option in options)
        ):
            raise ValidationError({'attributes': _(
                'Attribute %(position)d must be an object with a name and a type, and can have options.'
            ) % {'position': position}})
        name = entry['name'].strip()
        if not name:
            raise ValidationError({'attributes': _('An attribute has no name.')})
        if len(name) > longest:
            raise ValidationError({'attributes': _(
                'The name of attribute %(position)d is longer than %(count)d characters.'
            ) % {'position': position, 'count': longest}})
        if entry['type'] not in types:
            raise ValidationError({'attributes': _('Attribute %(name)s has an unknown type: %(type)s.') % {
                'name': name, 'type': entry['type'],
            }})
        options = [option.strip() for option in options]
        if entry['type'] not in OPTION_TYPES and options:
            raise ValidationError({'attributes': _(
                'Attribute %(name)s is not a dropdown or multi-select and takes no options.'
            ) % {'name': name}})
        if entry['type'] in OPTION_TYPES and not options:
            raise ValidationError({'attributes': _('Attribute %(name)s needs at least one option.') % {'name': name}})
        if any(not option or ',' in option for option in options):
            raise ValidationError({'attributes': _(
                'An option of attribute %(name)s is empty or holds a comma.'
            ) % {'name': name}})
        rows.append((name, entry['type'], options))
    duplicates = duplicate_attribute_names(template, [name for name, field_type, options in rows])
    if duplicates:
        raise ValidationError({'attributes': _('Attribute names must be unique: %(names)s.') % {
            'names': ', '.join(duplicates),
        }})
    return rows


def replace_sections(template, sections):
    template.sections.all().delete()

    ref_to_section = {}
    created = []
    for s in sections:
        section = TemplateSection.objects.create(
            template=template,
            title=s['title'],
            description=s['description'],
            number=s['number'],
            order=s['order'],
        )
        if s['ref']:
            ref_to_section[s['ref']] = section
        created.append((section, s['parent_ref']))

    for section, parent_ref in created:
        if parent_ref and parent_ref in ref_to_section:
            section.parent = ref_to_section[parent_ref]
            section.save(update_fields=['parent'])


def replace_attributes(template, attributes):
    template.attributes.filter(is_builtin=False).delete()
    order = template.attributes.filter(is_builtin=True).count()
    for name, field_type, options in attributes:
        TemplateAttribute.objects.create(
            template=template,
            name=name,
            field_type=field_type,
            options=options,
            is_builtin=False,
            order=order,
        )
        order += 1


def save_template(template, sections, attributes):
    with transaction.atomic():
        template.save()
        if sections is not None:
            replace_sections(template, sections)
        if attributes is not None:
            replace_attributes(template, attributes)
