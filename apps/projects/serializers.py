import os

from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import serializers

from apps.projects.sanitize import sanitize_rich_text

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


def _validate_image_field(value):
    if value is None:
        return value
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError(
            _('Image type "%(ext)s" is not allowed. Use PNG, JPG, GIF, or WebP.') % {'ext': ext}
        )
    if value.size > MAX_IMAGE_SIZE:
        raise serializers.ValidationError(_('Image size exceeds 5 MB limit.'))
    return value


def item_image_url(item, slug=None):
    if not item.image:
        return None
    return reverse('item_image', kwargs={'slug': slug or item.project.slug, 'public_key': item.public_key})


class ItemImageURLMixin:

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['image'] = item_image_url(instance, self._project_slug(instance))
        return data

    def _project_slug(self, instance):
        view = self.context.get('view')
        if view is not None and hasattr(view, 'get_project'):
            return view.get_project().slug
        return instance.project.slug


from apps.projects.models import (
    Attachment,
    Comment,
    Item,
    ItemAttributeValue,
    ItemTag,
    Project,
    ProjectMembership,
    ProjectVersion,
    SavedView,
    Section,
    Tag,
    TraceabilityLink,
)


class SectionSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()
    parent_id = serializers.IntegerField(source='parent.pk', allow_null=True, read_only=True)

    class Meta:
        model = Section
        fields = ['id', 'public_key', 'title', 'description', 'number', 'order', 'parent', 'parent_id', 'item_count']

    def get_item_count(self, obj):
        if hasattr(obj, '_item_count'):
            return obj._item_count
        return obj.item_count


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'is_preset']


class ItemAttributeValueSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source='attribute.name', read_only=True)
    attribute_type = serializers.CharField(source='attribute.field_type', read_only=True)
    display_value = serializers.SerializerMethodField()

    class Meta:
        model = ItemAttributeValue
        fields = ['id', 'attribute', 'attribute_name', 'attribute_type', 'value', 'display_value']

    def get_display_value(self, obj):
        view = self.context.get('view')
        user_names = view.user_names() if view is not None and hasattr(view, 'user_names') else None
        return obj.attribute.display_value(obj.value, user_names)


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_size_display = serializers.CharField(read_only=True)
    file_type_icon = serializers.CharField(read_only=True)

    class Meta:
        model = Attachment
        fields = [
            'id', 'public_key', 'filename', 'file', 'file_size', 'file_size_display',
            'file_type_icon', 'uploaded_by', 'uploaded_by_name', 'uploaded_at',
        ]
        read_only_fields = ['uploaded_by', 'uploaded_at', 'file_size', 'filename']

    def get_uploaded_by_name(self, obj):
        return str(obj.uploaded_by)


class TraceabilityLinkSerializer(serializers.ModelSerializer):
    source_item_id = serializers.CharField(source='source_item.item_id', read_only=True)
    target_item_id = serializers.CharField(source='target_item.item_id', read_only=True)
    target_project_name = serializers.CharField(source='target_item.project.name', read_only=True)
    source_project_name = serializers.CharField(source='source_item.project.name', read_only=True)
    link_type_display = serializers.CharField(source='get_link_type_display', read_only=True)

    class Meta:
        model = TraceabilityLink
        fields = [
            'id', 'public_key', 'source_item', 'target_item', 'link_type', 'link_type_display',
            'source_item_id', 'target_item_id', 'target_project_name', 'source_project_name',
            'created_by', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']

    def validate_source_item(self, value):
        view = self.context.get('view')
        if view and hasattr(view, 'get_project'):
            project = view.get_project()
            if value.project_id != project.pk:
                raise serializers.ValidationError(
                    _('Source item must belong to the current project.')
                )
        return value

    def validate_target_item(self, value):
        user = self.context['request'].user
        if not value.project.get_user_role(user):
            raise serializers.ValidationError(
                _("You do not have access to the target item's project.")
            )
        return value


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_initials = serializers.SerializerMethodField()
    author_color = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'public_key', 'text', 'parent', 'author', 'author_name',
            'author_initials', 'author_color', 'created_at',
        ]
        read_only_fields = ['author', 'created_at']

    def get_author_name(self, obj):
        return str(obj.author)

    def get_author_initials(self, obj):
        return obj.author.get_initials()

    def get_author_color(self, obj):
        return obj.author.avatar_color


class ItemListSerializer(ItemImageURLMixin, serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    attribute_values = ItemAttributeValueSerializer(many=True, read_only=True)
    assignee_name = serializers.SerializerMethodField()
    assignee_initials = serializers.SerializerMethodField()
    assignee_color = serializers.SerializerMethodField()
    section_number = serializers.CharField(source='section.number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'public_key', 'item_id', 'text', 'status', 'status_display',
            'priority', 'priority_display', 'section', 'section_number',
            'assignee', 'assignee_name', 'assignee_initials', 'assignee_color',
            'order', 'tags', 'attribute_values', 'image', 'image_caption', 'created_at', 'updated_at',
        ]

    def get_tags(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'item_tags' in obj._prefetched_objects_cache:
            tags = [it.tag for it in obj.item_tags.all()]
        else:
            tags = Tag.objects.filter(item_tags__item=obj)
        return TagSerializer(tags, many=True).data

    def get_assignee_name(self, obj):
        return str(obj.assignee) if obj.assignee else None

    def get_assignee_initials(self, obj):
        return obj.assignee.get_initials() if obj.assignee else None

    def get_assignee_color(self, obj):
        return obj.assignee.avatar_color if obj.assignee else None

    def validate_text(self, value):
        return sanitize_rich_text(value)

    def validate_image(self, value):
        return _validate_image_field(value)


class ItemDetailSerializer(ItemListSerializer):
    attribute_values = ItemAttributeValueSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    outgoing_links = TraceabilityLinkSerializer(many=True, read_only=True)
    incoming_links = TraceabilityLinkSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    section_title = serializers.CharField(source='section.title', read_only=True)

    class Meta(ItemListSerializer.Meta):
        fields = ItemListSerializer.Meta.fields + [
            'attribute_values', 'attachments', 'comments',
            'outgoing_links', 'incoming_links',
            'created_by_name', 'section_title',
        ]

    def get_created_by_name(self, obj):
        return str(obj.created_by)


class ItemCreateSerializer(ItemImageURLMixin, serializers.ModelSerializer):
    attribute_values = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False, default=list
    )
    insert_before = serializers.SlugRelatedField(
        slug_field='public_key', queryset=Item.objects.all(), write_only=True, required=False
    )
    insert_after = serializers.SlugRelatedField(
        slug_field='public_key', queryset=Item.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = Item
        fields = [
            'id', 'public_key', 'section', 'text', 'status', 'priority', 'assignee', 'image', 'image_caption',
            'attribute_values', 'insert_before', 'insert_after',
        ]
        read_only_fields = ['id', 'public_key']

    def validate(self, attrs):
        before = attrs.get('insert_before')
        after = attrs.get('insert_after')
        if before and after:
            raise serializers.ValidationError(_('Send insert_before or insert_after, not both.'))
        anchor = before or after
        if anchor and anchor.section_id != getattr(attrs.get('section'), 'pk', None):
            field = 'insert_before' if before else 'insert_after'
            raise serializers.ValidationError({field: _('The item is not in the chosen section.')})
        return attrs

    def validate_text(self, value):
        return sanitize_rich_text(value)

    def validate_image(self, value):
        return _validate_image_field(value)

    def validate_section(self, value):
        view = self.context.get('view')
        if view and hasattr(view, 'get_project'):
            project = view.get_project()
            if value.project_id != project.pk:
                raise serializers.ValidationError(_('Section does not belong to this project.'))
        return value


class ItemInlineEditSerializer(serializers.Serializer):
    field = serializers.ChoiceField(choices=['text', 'status', 'priority', 'assignee', 'image_caption'])
    value = serializers.CharField(allow_blank=True, allow_null=True)


class ItemReorderSerializer(serializers.Serializer):
    items = serializers.ListField(
        child=serializers.DictField()
    )


class BulkOperationSerializer(serializers.Serializer):
    ACTION_CHOICES = [
        ('set_status', gettext_lazy('Set Status')),
        ('set_priority', gettext_lazy('Set Priority')),
        ('add_tag', gettext_lazy('Add Tag')),
        ('delete', gettext_lazy('Delete')),
    ]
    item_ids = serializers.ListField(child=serializers.IntegerField())
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    value = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        from apps.projects.models import Item
        action = data.get('action')
        value = data.get('value', '')

        if action == 'set_status':
            valid_statuses = dict(Item.STATUS_CHOICES)
            if value not in valid_statuses:
                raise serializers.ValidationError({
                    'value': _('Invalid status "%(value)s". Must be one of: %(choices)s') % {'value': value, 'choices': list(valid_statuses.keys())}
                })
        elif action == 'set_priority':
            valid_priorities = dict(Item.PRIORITY_CHOICES)
            if value not in valid_priorities:
                raise serializers.ValidationError({
                    'value': _('Invalid priority "%(value)s". Must be one of: %(choices)s') % {'value': value, 'choices': list(valid_priorities.keys())}
                })
        elif action == 'add_tag':
            if not value.isdigit():
                raise serializers.ValidationError({'value': _('Give the id of the tag to add.')})

        return data


class SavedViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedView
        fields = ['id', 'public_key', 'name', 'filters', 'is_default', 'created_at']
        read_only_fields = ['created_at']


class MemberPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMembership
        fields = ['preferences']


class CollaboratorSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_initials = serializers.SerializerMethodField()
    user_color = serializers.SerializerMethodField()

    class Meta:
        model = ProjectMembership
        fields = ['id', 'public_key', 'user', 'role', 'user_name', 'user_email', 'user_initials', 'user_color', 'added_at']

    def get_user_name(self, obj):
        return str(obj.user)

    def get_user_initials(self, obj):
        return obj.user.get_initials()

    def get_user_color(self, obj):
        return obj.user.avatar_color


class ProjectVersionSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectVersion
        fields = ['id', 'public_key', 'version_number', 'changed_by', 'changed_by_name', 'changed_at', 'change_summary', 'item_count']

    def get_changed_by_name(self, obj):
        return str(obj.changed_by)
