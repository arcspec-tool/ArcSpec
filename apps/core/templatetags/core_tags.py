import json
import re

from django import template
from django.urls import resolve, reverse
from django.utils.safestring import mark_safe
from django.utils.timesince import timesince
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.projects.sanitize import sanitize_rich_text as _sanitize_rich_text

register = template.Library()


@register.filter
def initials(user):
    first = user.first_name[:1].upper() if user.first_name else ''
    last = user.last_name[:1].upper() if user.last_name else ''
    result = f"{first}{last}"
    return result or user.email[:2].upper()


@register.filter
def avatar_color(user):
    return user.avatar_color


@register.inclusion_tag('components/_avatar.html')
def avatar(user, size='sm'):
    return {
        'user': user,
        'size': size,
        'initials_text': initials(user),
        'color': user.avatar_color,
    }


STATUS_BADGE_MAP = {
    'active': (gettext_lazy('Active'), 'status-active'),
    'draft': (gettext_lazy('Draft'), 'status-draft'),
    'in-review': (gettext_lazy('In Review'), 'status-in-review'),
    'archived': (gettext_lazy('Archived'), 'status-archived'),
    'approved': (gettext_lazy('Approved'), 'status-approved'),
    'rejected': (gettext_lazy('Rejected'), 'status-rejected'),
    'inactive': (gettext_lazy('Inactive'), 'status-archived'),
    'builtin': (gettext_lazy('Built-in'), 'status-draft'),
    'public': (gettext_lazy('Public'), 'status-active'),
    'private': (gettext_lazy('Private'), 'status-other'),
}

PRIORITY_BADGE_MAP = {
    'high': (gettext_lazy('High'), 'priority-high'),
    'medium': (gettext_lazy('Medium'), 'priority-medium'),
    'low': (gettext_lazy('Low'), 'priority-low'),
}

ROLE_BADGE_MAP = {
    'admin': (gettext_lazy('Admin'), 'collab-role-admin'),
    'editor': (gettext_lazy('Editor'), 'collab-role-editor'),
    'viewer': (gettext_lazy('Viewer'), 'collab-role-viewer'),
}

SYSTEM_ROLE_BADGE_MAP = {
    'admin': (gettext_lazy('Administrator'), 'role-admin'),
    'user': (gettext_lazy('User'), 'role-user'),
    'viewer': (gettext_lazy('Viewer'), 'role-viewer'),
}


@register.inclusion_tag('components/_status_pill.html')
def status_badge(status):
    label, css = STATUS_BADGE_MAP.get(status, (status, 'status-other'))
    return {'label': label, 'css_class': css}


@register.inclusion_tag('components/_badge.html')
def priority_badge(priority):
    label, css = PRIORITY_BADGE_MAP.get(priority, (priority, 'priority-other'))
    return {'label': label, 'css_class': css}


@register.inclusion_tag('components/_role_badge.html')
def role_badge(role):
    label, css = ROLE_BADGE_MAP.get(role, (role, 'collab-role-viewer'))
    return {'label': label, 'css_class': css}


@register.inclusion_tag('components/_status_pill.html')
def system_role_badge(role):
    label, css = SYSTEM_ROLE_BADGE_MAP.get(role, (role, 'role-viewer'))
    return {'label': label, 'css_class': css}


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key, 0)
    return 0


_SHORT_UNITS = {
    'minutes': gettext_lazy('min'),
    'minute': gettext_lazy('min'),
    'hours': gettext_lazy('h'),
    'hour': gettext_lazy('h'),
    'days': gettext_lazy('d'),
    'day': gettext_lazy('d'),
    'weeks': gettext_lazy('w'),
    'week': gettext_lazy('w'),
    'months': gettext_lazy('mo'),
    'month': gettext_lazy('mo'),
    'years': gettext_lazy('y'),
    'year': gettext_lazy('y'),
}
_UNIT_RE = re.compile(r'\b(' + '|'.join(_SHORT_UNITS.keys()) + r')\b')


@register.filter
def short_timesince(value):
    try:
        raw = timesince(value)
    except Exception:
        return ''
    first = raw.split(',')[0].strip()
    short = _UNIT_RE.sub(lambda m: str(_SHORT_UNITS[m.group()]), first)
    return re.sub(r'(\d+)\s+(\w+)', r'\1\2', short)


@register.filter
def time_ago(value):
    short = short_timesince(value)
    if not short:
        return ''
    if short.startswith('0'):
        return _('just now')
    return _('%(time)s ago') % {'time': short}


@register.filter
def to_json(value):
    return json.dumps(value)


@register.filter
def strip_rich_text(value):
    if not value:
        return ''
    from django.utils.html import strip_tags
    text = strip_tags(value)
    text = text.replace('\xa0', ' ').replace('&nbsp;', ' ')
    return re.sub(r' {2,}', ' ', text).strip()


_P_TAG_RE = re.compile(r'</?p\b[^>]*>', re.IGNORECASE)


@register.filter
def sanitize_rich_text(value):
    if not value:
        return ''
    html = _sanitize_rich_text(value)
    html = re.sub(r'</p>\s*<p\b[^>]*>', '<br>', html, flags=re.IGNORECASE)
    html = _P_TAG_RE.sub('', html)
    return mark_safe(html.strip())


@register.simple_tag(takes_context=True)
def active_link(context, url_name, css_class='active'):
    try:
        request = context['request']
        current = resolve(request.path_info).url_name
        if current == url_name:
            return css_class
    except Exception:
        pass
    return ''


MESSAGE_TYPES = {'error': 'danger', 'debug': 'info'}


@register.simple_tag(takes_context=True)
def page_messages(context):
    return [
        {'message': str(message), 'type': MESSAGE_TYPES.get(message.level_tag, message.level_tag)}
        for message in context.get('messages', [])
    ]
