import re
import uuid
from dataclasses import dataclass
from typing import Callable

from django.http import Http404
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext as _

SLUG = re.compile(r'^[-a-zA-Z0-9_]{1,100}$')
CONFIRM_VARIANTS = ('danger', 'warning', 'primary')
AJAX_HEADER = 'XMLHttpRequest'


@dataclass(frozen=True)
class ModalSpec:
    name: str
    template: str
    context: Callable
    params: tuple
    modal_id: str
    size: str
    scrollable: bool


_registry = {}


def register(name, template, params=(), modal_id=None, size='', scrollable=False):
    def decorator(context):
        _registry[name] = ModalSpec(
            name=name,
            template=template,
            context=context,
            params=tuple(params),
            modal_id=modal_id or f'{name}Modal',
            size=size,
            scrollable=scrollable,
        )
        return context
    return decorator


def get(name):
    return _registry.get(name)


def names():
    return sorted(_registry)


def discover():
    autodiscover_modules('modals')


def is_ajax(request):
    return request.headers.get('X-Requested-With') == AJAX_HEADER


def render_modal(request, name, context, status=200):
    spec = _registry[name]
    context = dict(context)
    context.update({
        'modal_name': spec.name,
        'modal_id': spec.modal_id,
        'modal_size': spec.size,
        'modal_scrollable': spec.scrollable,
    })
    response = render(request, spec.template, context, status=status)
    response['Cache-Control'] = 'no-store'
    patch_vary_headers(response, ('X-Requested-With',))
    return response


def key_param(params, name):
    value = params.get(name)
    if not value:
        raise Http404
    try:
        return uuid.UUID(value)
    except ValueError:
        raise Http404


def slug_param(params, name):
    value = params.get(name)
    if not value or not SLUG.match(value):
        raise Http404
    return value


def text_param(params, name, default='', max_length=500):
    value = (params.get(name) or '').strip()
    return value[:max_length] if value else default


@register('confirm', 'modals/_confirm.html', params=('title', 'message', 'confirm_label', 'variant'), modal_id='confirmModal', size='sm')
def confirm(request, params):
    variant = params.get('variant') or 'danger'
    if variant not in CONFIRM_VARIANTS:
        variant = 'danger'
    return {
        'title': text_param(params, 'title', _('Confirm'), 200),
        'message': text_param(params, 'message', _('Are you sure?')),
        'confirm_label': text_param(params, 'confirm_label', _('Confirm'), 60),
        'variant': variant,
    }


@register('sign_out', 'modals/_sign_out.html', modal_id='signOutModal', size='sm')
def sign_out(request, params):
    return {}
