from apps.accounts.models import User
from apps.core.mixins import EDITOR_ROLES
from apps.projects.queries import audit_row
from apps.projects.sanitize import plain_text


def stamp(value):
    return value.isoformat()


def person(user):
    return {'name': str(user), 'email': user.email} if user else None


def project_row(project):
    return {
        'slug': project.slug,
        'name': project.name,
        'description': project.description,
        'status': project.status,
        'template': project.template.name,
        'role': project.user_role,
        'item_count': project.items_total,
        'member_count': project.members_total,
        'updated_at': stamp(project.updated_at),
    }


def project_detail(project, role, memberships):
    template = project.template
    return {
        'slug': project.slug,
        'name': project.name,
        'description': project.description,
        'status': project.status,
        'template': {
            'public_key': str(template.public_key),
            'name': template.name,
            'doc_type': template.doc_type,
            'item_prefix': template.item_id_prefix,
        },
        'members': [{'name': str(m.user), 'email': m.user.email, 'role': m.role} for m in memberships],
        'role': role,
        'can_write': role in EDITOR_ROLES and project.status != 'archived',
        'created_at': stamp(project.created_at),
        'updated_at': stamp(project.updated_at),
    }


def section_tree(root_sections, children_map):
    def node(section):
        return {
            'public_key': str(section.public_key),
            'number': section.number,
            'title': section.title,
            'description': section.description,
            'item_count': section.own_items,
            'total_items': section.total_items,
            'children': [node(child) for child in children_map.get(section.pk, [])],
        }
    return [node(section) for section in root_sections]


def user_emails(items):
    ids = set()
    for item in items:
        for value in item.attribute_values.all():
            if value.attribute.field_type == 'user' and value.value.isdigit():
                ids.add(int(value.value))
    if not ids:
        return {}
    return {str(user.pk): user.email for user in User.objects.filter(pk__in=ids)}


def attribute_value(value, emails):
    if value.attribute.field_type == 'user':
        return emails.get(value.value, value.value)
    return value.value


def item_row(item, emails):
    return {
        'item_id': item.item_id,
        'public_key': str(item.public_key),
        'section': item.section.number,
        'text': item.text,
        'status': item.status,
        'priority': item.priority,
        'assignee': person(item.assignee),
        'tags': [item_tag.tag.name for item_tag in item.item_tags.all()],
        'attributes': [
            {'name': value.attribute.name, 'value': attribute_value(value, emails)} for value in item.attribute_values.all()
        ],
    }


def link_row(link, other, roles):
    project = other.project
    allowed = project.pk in roles
    return {
        'public_key': str(link.public_key),
        'type': link.link_type,
        'item_id': other.item_id,
        'project_name': project.name,
        'project_slug': project.slug if allowed else None,
        'item_key': str(other.public_key) if allowed else None,
    }


def item_detail(item, tags, roles, emails):
    comments = list(item.comments.all())
    keys = {comment.pk: str(comment.public_key) for comment in comments}
    return {
        'item_id': item.item_id,
        'public_key': str(item.public_key),
        'section': {
            'public_key': str(item.section.public_key),
            'number': item.section.number,
            'title': item.section.title,
        },
        'text': item.text,
        'status': item.status,
        'priority': item.priority,
        'assignee': person(item.assignee),
        'tags': [{'public_key': str(tag.public_key), 'name': tag.name} for tag in tags],
        'attributes': [
            {'name': value.attribute.name, 'type': value.attribute.field_type, 'value': attribute_value(value, emails)}
            for value in item.attribute_values.all()
        ],
        'image_caption': item.image_caption,
        'has_image': bool(item.image),
        'attachments': [{'filename': a.filename, 'size': a.file_size} for a in item.attachments.all()],
        'comments': [
            {
                'public_key': keys[comment.pk],
                'author': str(comment.author),
                'text': comment.text,
                'created_at': stamp(comment.created_at),
                'reply_to': keys.get(comment.parent_id),
            }
            for comment in comments
        ],
        'outgoing_links': [link_row(link, link.target_item, roles) for link in item.outgoing_links.all()],
        'incoming_links': [link_row(link, link.source_item, roles) for link in item.incoming_links.all()],
        'created_by': str(item.created_by),
        'created_at': stamp(item.created_at),
        'updated_at': stamp(item.updated_at),
    }


def tag_row(tag):
    return {'public_key': str(tag.public_key), 'name': tag.name, 'preset': tag.is_preset}


def attribute_fields(entry):
    return {
        'public_key': entry['public_key'],
        'name': entry['name'],
        'type': entry['field_type'],
        'options': entry['options'],
        'builtin': entry['is_builtin'],
    }


def version_row(version):
    return {
        'public_key': str(version.public_key),
        'version': version.version_number,
        'changed_by': str(version.changed_by),
        'changed_at': stamp(version.changed_at),
        'summary': version.change_summary,
        'item_count': version.item_count,
    }


def audit_entry(entry):
    row = audit_row(entry)
    return {
        'action': row['action'],
        'target_type': row['target_type'],
        'target_id': row['target_id'],
        'user': row['user_name'],
        'details': row['details'],
        'created_at': row['created_at'],
    }


def template_row(template):
    return {
        'public_key': str(template.public_key),
        'name': template.name,
        'doc_type': template.doc_type,
        'description': template.description,
        'builtin': template.is_builtin,
        'section_count': template.section_total,
        'attribute_count': template.attribute_total,
    }


def template_sections(nodes):
    return [
        {
            'number': node['number'],
            'title': node['title'],
            'description': node['description'],
            'children': template_sections(node['children']),
        }
        for node in nodes
    ]


def template_detail(template, sections, attributes):
    return {
        'public_key': str(template.public_key),
        'name': template.name,
        'doc_type': template.doc_type,
        'description': template.description,
        'builtin': template.is_builtin,
        'sections': template_sections(sections),
        'attributes': [{'name': a.name, 'type': a.field_type, 'options': a.options} for a in attributes],
    }


def search_result(projects, items):
    return {
        'projects': [{'slug': p.slug, 'name': p.name, 'status': p.status} for p in projects],
        'items': [
            {
                'project': item.project.slug,
                'item_id': item.item_id,
                'public_key': str(item.public_key),
                'status': item.status,
                'section': item.section.number,
                'text': plain_text(item.text)[:100],
            }
            for item in items
        ],
    }
