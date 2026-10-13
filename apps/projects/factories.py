import factory
from django.db import models
from django.utils.text import slugify

from apps.accounts.factories import UserFactory
from apps.doctemplates.factories import TemplateFactory
from apps.projects.models import (
    Attachment,
    Comment,
    Item,
    ItemAttributeValue,
    ItemTag,
    Project,
    ProjectAttribute,
    ProjectMembership,
    ProjectVersion,
    SavedView,
    Section,
    Tag,
    TraceabilityLink,
)


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: f'Project {n}')
    slug = factory.LazyAttribute(lambda o: slugify(o.name))
    template = factory.SubFactory(TemplateFactory)
    created_by = factory.SubFactory(UserFactory)
    status = 'active'


class ProjectMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectMembership

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    role = 'editor'


class OwnedProjectFactory(ProjectFactory):
    class Meta:
        skip_postgeneration_save = True

    @factory.post_generation
    def owner_membership(obj, create, extracted, **kwargs):
        if create:
            ProjectMembership.objects.bulk_create([
                ProjectMembership(project=obj, user=obj.created_by, role='admin', added_by=obj.created_by),
            ])


class SectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Section

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f'Section {n}')
    number = factory.Sequence(lambda n: str(n + 1))
    order = factory.Sequence(lambda n: n)


class ItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Item
        exclude = ['_auto_id']

    _auto_id = True
    project = factory.SubFactory(ProjectFactory)
    section = factory.SubFactory(SectionFactory)
    item_id = factory.LazyAttribute(
        lambda o: f"{o.project.template.item_id_prefix}{o.project.next_item_number:03d}"
    )
    text = factory.Faker('sentence')
    status = 'draft'
    priority = 'medium'
    created_by = factory.SubFactory(UserFactory)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        super()._after_postgeneration(instance, create, results)
        if create:
            Project.objects.filter(pk=instance.project_id).update(
                next_item_number=models.F('next_item_number') + 1
            )
            instance.project.refresh_from_db()


class ProjectAttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectAttribute

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f'Attribute {n}')
    field_type = 'text'
    order = factory.Sequence(lambda n: n)


class ItemAttributeValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemAttributeValue

    item = factory.SubFactory(ItemFactory)
    attribute = factory.SubFactory(ProjectAttributeFactory)
    value = 'test value'


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag

    name = factory.Sequence(lambda n: f'Tag {n}')
    color = '#64748b'
    project = None
    is_preset = False


class PresetTagFactory(TagFactory):
    project = None
    is_preset = True


class ItemTagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemTag

    item = factory.SubFactory(ItemFactory)
    tag = factory.SubFactory(TagFactory)


class AttachmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Attachment

    item = factory.SubFactory(ItemFactory)
    file = factory.django.FileField(filename='test.pdf')
    filename = 'test.pdf'
    file_size = 1024
    uploaded_by = factory.SubFactory(UserFactory)


class TraceabilityLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TraceabilityLink

    source_item = factory.SubFactory(ItemFactory)
    target_item = factory.SubFactory(ItemFactory)
    link_type = 'related-to'
    created_by = factory.SubFactory(UserFactory)


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    item = factory.SubFactory(ItemFactory)
    author = factory.SubFactory(UserFactory)
    text = factory.Faker('paragraph')


class ProjectVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectVersion

    project = factory.SubFactory(ProjectFactory)
    version_number = '1.0'
    changed_by = factory.SubFactory(UserFactory)
    change_summary = 'Initial version'
    snapshot = factory.LazyFunction(lambda: {'sections': [], 'items': []})


class SavedViewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SavedView

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f'View {n}')
    filters = {}
