import uuid

from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.mcp.errors import ToolRefusal
from apps.projects.models import Tag


def as_key(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def item(queryset, value):
    key = as_key(value)
    found = (queryset.filter(public_key=key) if key else queryset.filter(item_id=value)).first()
    if found is None:
        raise ToolRefusal(_('Not found: item %(item)s.') % {'item': value})
    return found


def section(project, value):
    key = as_key(value)
    found = (project.sections.filter(public_key=key) if key else project.sections.filter(number=value)).first()
    if found is None:
        raise ToolRefusal(_('Not found: section %(section)s.') % {'section': value})
    return found


def tag(project, value):
    key = as_key(value)
    available = Tag.for_project(project)
    matches = list(available.filter(public_key=key) if key else available.filter(name=value).order_by('-is_preset'))
    if not matches:
        raise ToolRefusal(_('Not found: tag %(tag)s.') % {'tag': value})
    if len(matches) > 1:
        raise ToolRefusal(_('Tag %(tag)s names more than one tag; give a key: %(keys)s.') % {
            'tag': value, 'keys': ', '.join(str(match.public_key) for match in matches),
        })
    return matches[0]


def attribute(project, value):
    key = as_key(value)
    found = (project.attributes.filter(public_key=key) if key else project.attributes.filter(name=value)).first()
    if found is None:
        raise ToolRefusal(_('Not found: attribute %(attribute)s.') % {'attribute': value})
    return found


def assignee(project, email):
    found = User.objects.filter(email__iexact=email, assigned_items__project=project).first()
    if found is None:
        raise ToolRefusal(_('Not found: user %(email)s.') % {'email': email})
    return found


def audit_user(project, email):
    found = User.objects.filter(email__iexact=email, audit_logs__project=project).first()
    if found is None:
        raise ToolRefusal(_('Not found: user %(email)s.') % {'email': email})
    return found
