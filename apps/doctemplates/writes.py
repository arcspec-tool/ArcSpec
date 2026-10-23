from apps.doctemplates.models import TemplateAttribute, TemplateSection


def duplicate_attribute_names(template, names):
    names = list(names)
    if template is not None and template.pk:
        names += template.attributes.filter(is_builtin=True).values_list('name', flat=True)
    return sorted({name for name in names if names.count(name) > 1})


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
