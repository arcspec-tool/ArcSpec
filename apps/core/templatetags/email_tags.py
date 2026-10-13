import base64
from functools import cache

from django import template
from django.contrib.staticfiles import finders

from apps.core import site

register = template.Library()


@cache
def _png_data_uri(path):
    with open(finders.find(path), 'rb') as image:
        return 'data:image/png;base64,' + base64.b64encode(image.read()).decode('ascii')


@register.simple_tag
def inline_png(path):
    return _png_data_uri(path)


@register.simple_tag
def site_url(path=''):
    return site.absolute_url(path)


@register.simple_tag
def site_host():
    return site.site_host()
