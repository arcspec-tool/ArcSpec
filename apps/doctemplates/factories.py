import factory

from apps.accounts.factories import UserFactory
from apps.doctemplates.models import Template, TemplateAttribute, TemplateSection


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    name = factory.Sequence(lambda n: f'Template {n}')
    doc_type = 'requirements'
    is_builtin = False
    created_by = factory.SubFactory(UserFactory)


class TemplateSectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateSection

    template = factory.SubFactory(TemplateFactory)
    title = factory.Sequence(lambda n: f'Section {n}')
    number = factory.Sequence(lambda n: str(n + 1))
    order = factory.Sequence(lambda n: n)


class TemplateAttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateAttribute

    template = factory.SubFactory(TemplateFactory)
    name = factory.Sequence(lambda n: f'Attribute {n}')
    field_type = 'text'
    order = factory.Sequence(lambda n: n)
