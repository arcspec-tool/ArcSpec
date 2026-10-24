from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.doctemplates.models import Template, TemplateAttribute, TemplateSection


def count_per_template(queryset):
    counted = queryset.filter(template=OuterRef('pk')).order_by().values('template').annotate(n=Count('pk')).values('n')[:1]
    return Coalesce(Subquery(counted), 0)


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


def template_list_queryset(user, q='', doc_type=''):
    from apps.projects.models import Project
    qs = Template.objects.visible_to(user).select_related('created_by').annotate(
        usage_count=count_per_template(Project.objects.all()),
        section_total=count_per_template(TemplateSection.objects.all()),
        attribute_total=count_per_template(TemplateAttribute.objects.all()),
    ).order_by('-is_builtin', 'display_order', 'name')
    if q:
        qs = qs.filter(name__icontains=q)
    if doc_type:
        qs = qs.filter(doc_type=doc_type)
    return qs
