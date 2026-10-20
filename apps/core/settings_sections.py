from dataclasses import dataclass
from typing import Callable

from django.template.loader import render_to_string
from django.utils.module_loading import autodiscover_modules


@dataclass(frozen=True)
class SettingsSection:
    name: str
    template: str
    context: Callable


_registry = {}


def register(name, template):
    def decorator(context):
        _registry[name] = SettingsSection(name=name, template=template, context=context)
        return context
    return decorator


def discover():
    autodiscover_modules('settings_sections')


def rendered(request):
    sections = []
    for section in _registry.values():
        context = section.context(request)
        if context is not None:
            sections.append(render_to_string(section.template, context, request=request))
    return sections
