from apps.projects.models import Section


def renumber_sections(project, actor=None):
    sections = list(
        Section.objects.filter(project=project).order_by('order')
    )

    children_map = {}
    roots = []
    for section in sections:
        if section.parent_id is None:
            roots.append(section)
        else:
            children_map.setdefault(section.parent_id, []).append(section)

    def _renumber(nodes, prefix=''):
        for i, node in enumerate(nodes, start=1):
            number = f'{prefix}{i}' if not prefix else f'{prefix}.{i}'
            if not prefix:
                number = str(i)
            if node.number != number:
                node.number = number
                node._actor = actor
                node.save(update_fields=['number'])
            children = children_map.get(node.pk, [])
            if children:
                _renumber(children, prefix=number)

    _renumber(roots)
