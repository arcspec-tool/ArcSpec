from django.db import transaction
from django.db import models
from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.notifications.models import AuditLog
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
    attribute_user_names,
)
from apps.projects.permissions import IsProjectAdmin, IsProjectEditorOrAdmin, IsProjectMember, ProjectNotArchived
from apps.projects.sanitize import plain_text, sanitize_rich_text
from apps.projects.serializers import (
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_IMAGE_SIZE,
    AttachmentSerializer,
    BulkOperationSerializer,
    CollaboratorSerializer,
    CommentSerializer,
    ItemCreateSerializer,
    ItemDetailSerializer,
    ItemInlineEditSerializer,
    ItemListSerializer,
    ItemReorderSerializer,
    MemberPreferencesSerializer,
    ProjectVersionSerializer,
    SavedViewSerializer,
    SectionSerializer,
    TagSerializer,
    TraceabilityLinkSerializer,
    item_image_url,
)
from apps.projects.signals import create_version


class GlobalSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if len(q) < 2:
            return Response({'projects': [], 'items': []})

        user_projects = Project.objects.for_user(request.user)

        projects = user_projects.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )[:5]
        project_data = [
            {
                'id': p.pk,
                'name': p.name,
                'slug': p.slug,
                'status': p.status,
                'color': p.color,
            }
            for p in projects
        ]

        items = Item.objects.filter(
            project__in=user_projects
        ).filter(
            Q(item_id__icontains=q) | Q(text__icontains=q)
        ).select_related('project', 'section')[:10]
        item_data = [
            {
                'id': i.pk,
                'public_key': str(i.public_key),
                'item_id': i.item_id,
                'text': plain_text(i.text)[:100],
                'status': i.status,
                'project_name': i.project.name,
                'project_slug': i.project.slug,
                'section_number': i.section.number if i.section else '',
            }
            for i in items
        ]

        return Response({
            'projects': project_data,
            'items': item_data,
        })


class ProjectAPIMixin:

    def get_project(self):
        if not hasattr(self, '_project'):
            self._project = get_object_or_404(Project, slug=self.kwargs['slug'])
        return self._project

    def user_names(self):
        if not hasattr(self, '_user_names'):
            self._user_names = attribute_user_names(self.get_project())
        return self._user_names


class ItemScopedMixin(ProjectAPIMixin):

    def get_item(self):
        if not hasattr(self, '_item'):
            self._item = get_object_or_404(Item, public_key=self.kwargs['item_key'], project=self.get_project())
        return self._item

    def create(self, request, *args, **kwargs):
        self.get_item()
        return super().create(request, *args, **kwargs)



class SectionListView(ProjectAPIMixin, generics.ListAPIView):
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Section.objects.filter(project=self.get_project()).select_related(
            'parent'
        ).annotate(_item_count=Count('items')).order_by('order')


class SectionReorderView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def post(self, request, slug):
        sections = request.data.get('sections', [])
        with transaction.atomic():
            for entry in sections:
                Section.objects.filter(
                    pk=entry['id'], project=self.get_project()
                ).update(order=entry['order'])
        return Response({'status': 'ok'})



def _save_attribute_values(item, attribute_values, project):
    from apps.projects.models import ProjectAttribute
    valid_attr_ids = set(
        ProjectAttribute.objects.filter(project=project).values_list('pk', flat=True)
    )
    with transaction.atomic():
        item.attribute_values.all().delete()
        for av in attribute_values:
            attr_id = av.get('attribute')
            value = av.get('value', '')
            try:
                attr_id_int = int(attr_id)
            except (ValueError, TypeError):
                continue
            if attr_id_int in valid_attr_ids:
                ItemAttributeValue.objects.create(
                    item=item, attribute_id=attr_id_int, value=str(value)
                )


class ItemListCreateView(ProjectAPIMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ItemCreateSerializer
        return ItemListSerializer

    def get_queryset(self):
        project = self.get_project()
        qs = Item.objects.filter(project=project).select_related(
            'section', 'assignee'
        ).prefetch_related(
            'item_tags__tag', 'attribute_values__attribute'
        ).order_by('section__order', 'order')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        priority_filter = self.request.query_params.get('priority')
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        tag_filter = self.request.query_params.get('tag')
        if tag_filter:
            qs = qs.filter(item_tags__tag__name=tag_filter)
        section_filter = self.request.query_params.get('section')
        if section_filter:
            qs = qs.filter(section_id=section_filter)
        search = self.request.query_params.get('search')
        if search and len(search) >= 2:
            qs = qs.filter(Q(item_id__icontains=search) | Q(text__icontains=search))

        return qs.distinct()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsProjectEditorOrAdmin(), ProjectNotArchived()]
        return super().get_permissions()

    @transaction.atomic
    def perform_create(self, serializer):
        project = self.get_project()
        locked_project = Project.objects.select_for_update().get(pk=project.pk)
        item_id = locked_project.generate_item_id()
        Project.objects.filter(pk=project.pk).update(
            next_item_number=F('next_item_number') + 1
        )
        section = serializer.validated_data.get('section')
        insert_before = serializer.validated_data.pop('insert_before', None)
        insert_after = serializer.validated_data.pop('insert_after', None)
        anchor = insert_before or insert_after
        if anchor:
            next_order = anchor.order if insert_before else anchor.order + 1
            Item.objects.filter(
                project=project, section=section, order__gte=next_order
            ).update(order=F('order') + 1)
        else:
            max_order = Item.objects.filter(
                project=project, section=section
            ).aggregate(m=models.Max('order'))['m']
            next_order = (max_order or 0) + 1
        attribute_values = serializer.validated_data.pop('attribute_values', [])
        serializer.save(
            project=project,
            item_id=item_id,
            created_by=self.request.user,
            order=next_order,
        )
        if attribute_values:
            _save_attribute_values(serializer.instance, attribute_values, project)


class ItemRetrieveUpdateDestroyView(ProjectAPIMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ItemDetailSerializer
    lookup_field = 'public_key'
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Item.objects.filter(project=self.get_project()).select_related(
            'section', 'assignee', 'created_by'
        ).prefetch_related(
            'attribute_values__attribute', 'attachments__uploaded_by', 'comments__author',
            'outgoing_links__target_item__project', 'outgoing_links__source_item__project',
            'incoming_links__source_item__project', 'incoming_links__target_item__project',
        )

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsAuthenticated(), IsProjectEditorOrAdmin(), ProjectNotArchived()]
        return super().get_permissions()

    @transaction.atomic
    def perform_update(self, serializer):
        attribute_values = self.request.data.get('attribute_values')
        serializer.instance._actor = self.request.user
        serializer.save()
        if attribute_values is not None:
            _save_attribute_values(serializer.instance, attribute_values, self.get_project())

    def perform_destroy(self, instance):
        instance._actor = self.request.user
        instance.delete()


class ItemInlineEditView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def patch(self, request, slug, public_key):
        project = self.get_project()
        item = get_object_or_404(Item, public_key=public_key, project=project)
        serializer = ItemInlineEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        field = serializer.validated_data['field']
        value = serializer.validated_data['value']

        if field == 'assignee':
            if value:
                assignee_id = int(value)
                from apps.accounts.models import User
                if not User.objects.filter(pk=assignee_id, is_active=True).exists():
                    return Response(
                        {'error': _('Assignee user not found or inactive.')},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not ProjectMembership.objects.filter(
                    project=project, user_id=assignee_id
                ).exists() and not User.objects.filter(
                    pk=assignee_id, system_role='admin'
                ).exists():
                    return Response(
                        {'error': _('Assignee must be a project member.')},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                item.assignee_id = assignee_id
            else:
                item.assignee = None
        else:
            if field == 'text':
                value = sanitize_rich_text(value)
            elif field == 'status':
                valid_statuses = dict(Item.STATUS_CHOICES)
                if value not in valid_statuses:
                    return Response(
                        {'error': _('Invalid status. Must be one of: %(choices)s') % {'choices': list(valid_statuses.keys())}},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            elif field == 'priority':
                valid_priorities = dict(Item.PRIORITY_CHOICES)
                if value not in valid_priorities:
                    return Response(
                        {'error': _('Invalid priority. Must be one of: %(choices)s') % {'choices': list(valid_priorities.keys())}},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            setattr(item, field, value)

        item._actor = request.user
        item.save()
        return Response(ItemListSerializer(item, context={'view': self}).data)


class ItemReorderView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def post(self, request, slug):
        project = self.get_project()
        serializer = ItemReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        section_ids = {
            entry['section'] for entry in serializer.validated_data['items']
            if 'section' in entry
        }
        if section_ids:
            valid_ids = set(
                Section.objects.filter(project=project, pk__in=section_ids)
                .values_list('pk', flat=True)
            )
            invalid = section_ids - valid_ids
            if invalid:
                return Response(
                    {'error': _('One or more sections do not belong to this project.')},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            for entry in serializer.validated_data['items']:
                update_fields = {'order': entry['order']}
                if 'section' in entry:
                    update_fields['section_id'] = entry['section']
                Item.objects.filter(
                    pk=entry['id'], project=project
                ).update(**update_fields)

        return Response({'status': 'ok'})


class ItemBulkOperationView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def post(self, request, slug):
        project = self.get_project()
        serializer = BulkOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item_ids = serializer.validated_data['item_ids']
        action = serializer.validated_data['action']
        value = serializer.validated_data.get('value', '')
        items = Item.objects.filter(pk__in=item_ids, project=project)
        affected = list(items.values_list('item_id', flat=True))

        if action == 'set_status':
            items.update(status=value)
        elif action == 'set_priority':
            items.update(priority=value)
        elif action == 'add_tag':
            tag = Tag.for_project(project).filter(pk=int(value)).first()
            if tag is None:
                return Response({'error': _('Tag not found.')}, status=status.HTTP_400_BAD_REQUEST)
            value = tag.name
            for item in items:
                ItemTag.objects.get_or_create(item=item, tag=tag)
        elif action == 'delete':
            for item in items:
                item._silent = True
                item.delete()

        action_map = {
            'set_status': 'status_changed',
            'set_priority': 'priority_changed',
            'add_tag': 'tag_added',
            'delete': 'deleted',
        }
        audit_action = action_map.get(action, 'bulk_updated')
        details = {'bulk': True, 'value': value}
        audit_entries = [
            AuditLog(
                project=project, user=request.user, action=audit_action,
                target_type='Item', target_id=iid, details=details,
            )
            for iid in affected
        ]
        AuditLog.objects.bulk_create(audit_entries)
        if action == 'delete' and affected:
            create_version(project, request.user, ngettext(
                'Deleted %(count)d items',
                'Deleted %(count)d items',
                len(affected),
            ) % {'count': len(affected)})

        return Response({'status': 'ok', 'count': len(affected) if action != 'delete' else 0})


class ItemImageUploadView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def post(self, request, slug, public_key):
        project = self.get_project()
        item = get_object_or_404(Item, public_key=public_key, project=project)
        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return Response({'error': _('No image file provided.')}, status=status.HTTP_400_BAD_REQUEST)

        import os
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return Response(
                {'error': _('Image type "%(ext)s" is not allowed. Use PNG, JPG, GIF, or WebP.') % {'ext': ext}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded_file.size > MAX_IMAGE_SIZE:
            return Response(
                {'error': _('Image size exceeds 5 MB limit.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        had_image = bool(item.image)
        old_filename = item.image.name if item.image else None
        if item.image:
            item.image.delete(save=False)

        item.image = uploaded_file
        caption = request.data.get('image_caption', '').strip()
        if caption:
            item.image_caption = caption
        item._actor = request.user
        item.save()

        audit_details = {
            'field': 'image',
            'action': 'changed' if had_image else 'added',
            'filename': uploaded_file.name,
        }
        if had_image:
            audit_details['previous_filename'] = old_filename.split('/')[-1] if old_filename else None
        AuditLog.objects.create(
            project=project, user=request.user, action='edited',
            target_type='Item', target_id=item.item_id,
            details=audit_details,
        )

        return Response({
            'image': item_image_url(item, project.slug),
            'image_caption': item.image_caption,
        })

    def delete(self, request, slug, public_key):
        project = self.get_project()
        item = get_object_or_404(Item, public_key=public_key, project=project)
        if item.image:
            item.image.delete(save=False)
        item.image = None
        item.image_caption = ''
        item._actor = request.user
        item.save()

        AuditLog.objects.create(
            project=project, user=request.user, action='edited',
            target_type='Item', target_id=item.item_id,
            details={'field': 'image', 'action': 'removed'},
        )

        return Response({'status': 'ok'})


class ItemSearchView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get(self, request, slug):
        project = self.get_project()
        q = request.query_params.get('q', '')
        if len(q) < 2:
            return Response([])
        items = Item.objects.filter(project=project).search(q)[:20]
        return Response(ItemListSerializer(items, many=True, context={'view': self}).data)



class CommentListCreateView(ItemScopedMixin, generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember, ProjectNotArchived]

    def get_queryset(self):
        return Comment.objects.filter(item=self.get_item()).select_related('author')

    def perform_create(self, serializer):
        serializer.save(item=self.get_item(), author=self.request.user)


class CommentDestroyView(ProjectAPIMixin, generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, IsProjectMember, ProjectNotArchived]
    lookup_field = 'public_key'

    def get_queryset(self):
        return Comment.objects.filter(item__project=self.get_project())

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        project = self.get_project()
        role = project.get_user_role(request.user)
        if obj.author != request.user and role != 'admin':
            self.permission_denied(request)



class TagListView(ProjectAPIMixin, generics.ListAPIView):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Tag.for_project(self.get_project())


class TagCreateView(ProjectAPIMixin, generics.CreateAPIView):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def perform_create(self, serializer):
        serializer.save(
            project=self.get_project(),
            created_by=self.request.user,
        )


class ItemTagUpdateView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def put(self, request, slug, item_key):
        project = self.get_project()
        item = get_object_or_404(Item, public_key=item_key, project=project)
        tag_ids = request.data.get('tag_ids', [])
        valid_tag_ids = set(
            Tag.for_project(project).values_list('pk', flat=True)
        )
        for tag_id in tag_ids:
            if tag_id not in valid_tag_ids:
                return Response(
                    {'error': _('Tag %(tag)s is not available for this project.') % {'tag': tag_id}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        old_tags = set(Tag.objects.filter(item_tags__item=item).values_list('name', flat=True))
        ItemTag.objects.filter(item=item).delete()
        for tag_id in tag_ids:
            tag = get_object_or_404(Tag, pk=tag_id)
            ItemTag.objects.create(item=item, tag=tag)
        tags = Tag.objects.filter(item_tags__item=item)
        new_tags = set(tags.values_list('name', flat=True))
        added = new_tags - old_tags
        removed = old_tags - new_tags
        if added:
            AuditLog.objects.create(
                project=project, user=request.user, action='tag_added',
                target_type='Item', target_id=item.item_id,
                details={'tags': list(added)},
            )
        if removed:
            AuditLog.objects.create(
                project=project, user=request.user, action='tag_removed',
                target_type='Item', target_id=item.item_id,
                details={'tags': list(removed)},
            )
        return Response(TagSerializer(tags, many=True).data)



class AttachmentListCreateView(ItemScopedMixin, generics.ListCreateAPIView):
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Attachment.objects.filter(item=self.get_item()).select_related('uploaded_by')

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsProjectEditorOrAdmin(), ProjectNotArchived()]
        return super().get_permissions()

    ALLOWED_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.json', '.xml', '.yaml', '.yml', '.md',
    }

    def perform_create(self, serializer):
        item = self.get_item()
        uploaded_file = self.request.FILES.get('file')
        if not uploaded_file:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'file': _('No file was uploaded.')})

        import os
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'file': _('File type "%(ext)s" is not allowed.') % {'ext': ext}})

        from apps.administration.models import SystemSettings
        settings = SystemSettings.load()
        max_bytes = settings.max_attachment_size_mb * 1024 * 1024
        if uploaded_file.size > max_bytes:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({
                'file': _('File size exceeds the %(size)s MB limit.') % {'size': settings.max_attachment_size_mb}
            })

        serializer.save(
            item=item,
            uploaded_by=self.request.user,
            filename=uploaded_file.name,
            file_size=uploaded_file.size,
        )
        AuditLog.objects.create(
            project=item.project, user=self.request.user, action='attachment_added',
            target_type='Item', target_id=item.item_id,
            details={'filename': uploaded_file.name},
        )


class AttachmentDestroyView(ProjectAPIMixin, generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]
    lookup_field = 'public_key'

    def get_queryset(self):
        return Attachment.objects.filter(item__project=self.get_project())

    def perform_destroy(self, instance):
        item = instance.item
        filename = instance.filename
        super().perform_destroy(instance)
        AuditLog.objects.create(
            project=item.project, user=self.request.user, action='attachment_removed',
            target_type='Item', target_id=item.item_id,
            details={'filename': filename},
        )



class LinkListCreateView(ItemScopedMixin, generics.ListCreateAPIView):
    serializer_class = TraceabilityLinkSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        item = self.get_item()
        return TraceabilityLink.objects.filter(
            Q(source_item=item) | Q(target_item=item),
            Q(source_item__project=self.get_project()) | Q(target_item__project=self.get_project()),
        ).select_related(
            'source_item__project', 'target_item__project'
        ).order_by('-created_at')

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsProjectEditorOrAdmin(), ProjectNotArchived()]
        return super().get_permissions()

    def perform_create(self, serializer):
        link = serializer.save(created_by=self.request.user)
        source = link.source_item
        target = link.target_item
        AuditLog.objects.create(
            project=source.project, user=self.request.user, action='link_added',
            target_type='Item', target_id=source.item_id,
            details={'link_type': link.link_type, 'target': target.item_id},
        )


class LinkDestroyView(ProjectAPIMixin, generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]
    lookup_field = 'public_key'

    def get_queryset(self):
        return TraceabilityLink.objects.filter(
            Q(source_item__project=self.get_project()) |
            Q(target_item__project=self.get_project())
        )

    def perform_destroy(self, instance):
        source_item_id = instance.source_item.item_id
        target_item_id = instance.target_item.item_id
        project = instance.source_item.project
        link_type = instance.link_type
        super().perform_destroy(instance)
        AuditLog.objects.create(
            project=project, user=self.request.user, action='link_removed',
            target_type='Item', target_id=source_item_id,
            details={'link_type': link_type, 'target': target_item_id},
        )



class SavedViewListCreateView(ProjectAPIMixin, generics.ListCreateAPIView):
    serializer_class = SavedViewSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return SavedView.objects.filter(
            project=self.get_project(),
            user=self.request.user,
        )

    def perform_create(self, serializer):
        serializer.save(
            project=self.get_project(),
            user=self.request.user,
        )


class SavedViewDestroyView(ProjectAPIMixin, generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    lookup_field = 'public_key'

    def get_queryset(self):
        return SavedView.objects.filter(
            project=self.get_project(),
            user=self.request.user,
            is_default=False,
        )



class MemberPreferencesView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectMember]

    def _membership(self, request):
        membership = ProjectMembership.objects.filter(project=self.get_project(), user=request.user).first()
        if membership is None and not request.user.is_system_admin:
            raise Http404
        return membership

    def get(self, request, slug):
        membership = self._membership(request)
        return Response({'preferences': membership.preferences if membership else {}})

    def patch(self, request, slug):
        membership = self._membership(request)
        prefs = request.data.get('preferences', {})
        if not isinstance(prefs, dict):
            return Response(
                {'detail': _('preferences must be a JSON object.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if membership is None:
            return Response({'preferences': prefs, 'stored': False})
        membership.preferences.update(prefs)
        membership.save(update_fields=['preferences'])
        return Response({'preferences': membership.preferences, 'stored': True})



class CollaboratorListView(ProjectAPIMixin, generics.ListAPIView):
    serializer_class = CollaboratorSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return ProjectMembership.objects.filter(
            project=self.get_project()
        ).select_related('user').order_by('added_at')


class CollaboratorInviteView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectAdmin, ProjectNotArchived]

    def post(self, request, slug):
        project = self.get_project()
        email = request.data.get('email', '').strip()
        role = request.data.get('role', 'viewer')
        if role not in dict(ProjectMembership.ROLE_CHOICES):
            return Response({'error': _('Invalid role.')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'error': _('User not found or inactive.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ProjectMembership.objects.filter(project=project, user=user).exists():
            return Response(
                {'error': _('User is already a collaborator.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = ProjectMembership.objects.create(
            project=project, user=user, role=role, added_by=request.user
        )
        return Response(
            CollaboratorSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


class CollaboratorUpdateView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectAdmin, ProjectNotArchived]

    def _is_last_admin(self, membership):
        return (
            membership.role == 'admin'
            and membership.project.memberships.filter(role='admin').count() <= 1
        )

    def patch(self, request, slug, public_key):
        membership = get_object_or_404(
            ProjectMembership, public_key=public_key, project=self.get_project()
        )
        role = request.data.get('role')
        if role and role in dict(ProjectMembership.ROLE_CHOICES):
            if role != 'admin' and self._is_last_admin(membership):
                return Response(
                    {'error': _('Cannot demote the last project admin.')},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            membership.role = role
            membership._actor = request.user
            membership.save()
        return Response(CollaboratorSerializer(membership).data)

    def delete(self, request, slug, public_key):
        membership = get_object_or_404(
            ProjectMembership, public_key=public_key, project=self.get_project()
        )
        if self._is_last_admin(membership):
            return Response(
                {'error': _('Cannot remove the last project admin.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership._actor = request.user
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



class VersionListView(ProjectAPIMixin, generics.ListAPIView):
    serializer_class = ProjectVersionSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return ProjectVersion.objects.filter(
            project=self.get_project()
        ).select_related('changed_by')


class VersionRestoreView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectAdmin, ProjectNotArchived]

    def post(self, request, slug, public_key):
        project = self.get_project()
        version = get_object_or_404(ProjectVersion, public_key=public_key, project=project)
        snapshot = version.snapshot
        if not snapshot or 'sections' not in snapshot:
            return Response(
                {'error': _('This version has no snapshot data to restore.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            sections = self._restore_sections(project, snapshot['sections'])
            self._restore_items(project, snapshot.get('items', []), sections, request.user)
            self._delete_sections_not_in_snapshot(project, sections)
            AuditLog.objects.create(
                project=project,
                user=request.user,
                action='version_restored',
                target_type='Project',
                target_id=project.name[:50],
                details={'version': version.version_number},
            )
            create_version(project, request.user, _('Restored version %(version)s') % {'version': version.version_number})

        return Response({
            'status': 'ok',
            'message': _('Restored to version %(version)s') % {'version': version.version_number},
        })

    @staticmethod
    def _silent_save(instance):
        instance._silent = True
        instance.save()

    def _restore_sections(self, project, snapshot_sections):
        existing = {section.pk: section for section in project.sections.all()}
        restored = {}
        for data in snapshot_sections:
            section = existing.get(data['id']) or Section(project=project)
            section.title = data['title']
            section.number = data['number']
            section.order = data['order']
            section.description = data.get('description', section.description)
            self._silent_save(section)
            restored[data['id']] = section
        for data in snapshot_sections:
            section = restored[data['id']]
            parent = restored.get(data.get('parent_id'))
            parent_id = parent.pk if parent else None
            if section.parent_id != parent_id:
                section.parent_id = parent_id
                self._silent_save(section)
        return restored

    def _restore_items(self, project, snapshot_items, sections, user):
        existing = {item.pk: item for item in project.items.all()}
        by_item_id = {item.item_id: item for item in existing.values()}
        user_ids = {data.get('assignee_id') for data in snapshot_items} | {data.get('created_by_id') for data in snapshot_items}
        valid_users = set(User.objects.filter(pk__in=user_ids - {None}).values_list('pk', flat=True))
        valid_tags = set(Tag.for_project(project).values_list('pk', flat=True))
        valid_attributes = set(project.attributes.values_list('pk', flat=True))
        kept = set()
        for data in snapshot_items:
            section = sections.get(data['section_id'])
            if section is None:
                continue
            item = existing.get(data['id']) or by_item_id.get(data['item_id'])
            if item is None:
                created_by_id = data.get('created_by_id')
                item = Item(
                    project=project,
                    item_id=data['item_id'],
                    created_by_id=created_by_id if created_by_id in valid_users else user.pk,
                )
            assignee_id = data.get('assignee_id')
            item.section = section
            item.text = data['text']
            item.status = data['status']
            item.priority = data['priority']
            item.assignee_id = assignee_id if assignee_id in valid_users else None
            item.order = data['order']
            item.image_caption = data.get('image_caption', '')
            self._silent_save(item)
            kept.add(item.pk)
            ItemTag.objects.filter(item=item).delete()
            ItemTag.objects.bulk_create([
                ItemTag(item=item, tag_id=tag_id)
                for tag_id in data.get('tag_ids', []) if tag_id in valid_tags
            ])
            item.attribute_values.all().delete()
            ItemAttributeValue.objects.bulk_create([
                ItemAttributeValue(item=item, attribute_id=av['attribute_id'], value=av['value'])
                for av in data.get('attribute_values', []) if av['attribute_id'] in valid_attributes
            ])
        for item in existing.values():
            if item.pk not in kept:
                item._silent = True
                item.delete()

    @staticmethod
    def _delete_sections_not_in_snapshot(project, restored):
        doomed = {section.pk: section for section in project.sections.all() if section.pk not in restored}
        while doomed:
            leaves = [s for s in doomed.values() if not any(o.parent_id == s.pk for o in doomed.values())]
            if not leaves:
                break
            for section in leaves:
                pk = section.pk
                section._silent = True
                section.delete()
                del doomed[pk]



AUDIT_ACTION_GROUPS = {
    'collaboration': ('collaborator_added', 'collaborator_removed', 'collaborator_role_changed'),
}


class AuditLogListView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get(self, request, slug):
        project = self.get_project()
        qs = AuditLog.objects.filter(project=project).select_related('user')

        action_filter = request.query_params.get('action')
        if action_filter in AUDIT_ACTION_GROUPS:
            qs = qs.filter(action__in=AUDIT_ACTION_GROUPS[action_filter])
        elif action_filter and action_filter != 'all':
            qs = qs.filter(action=action_filter)
        user_filter = request.query_params.get('user')
        if user_filter:
            qs = qs.filter(user_id=user_filter)
        target_id_filter = request.query_params.get('target_id')
        if target_id_filter:
            qs = qs.filter(target_type='Item', target_id=target_id_filter)

        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 50))
        entries = list(qs[offset:offset + limit + 1])
        has_more = len(entries) > limit
        entries = entries[:limit]

        data = []
        for entry in entries:
            icon_data = AuditLog.ACTION_ICONS.get(entry.action, ('bi-circle', 'text-muted'))
            data.append({
                'id': entry.pk,
                'action': entry.action,
                'action_display': entry.get_action_display(),
                'target_type': entry.target_type,
                'target_id': entry.target_id,
                'user_name': str(entry.user),
                'user_initials': entry.user.get_initials(),
                'user_color': entry.user.avatar_color,
                'icon': icon_data[0],
                'icon_color': icon_data[1],
                'details': entry.details,
                'created_at': entry.created_at.isoformat(),
            })

        return Response({
            'results': data,
            'has_more': has_more,
        })



class ProjectAttributeListCreateView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def get(self, request, slug):
        project = self.get_project()
        attrs = project.attributes.order_by('order')
        data = [
            {
                'id': a.pk,
                'public_key': str(a.public_key),
                'name': a.name,
                'field_type': a.field_type,
                'options': a.options,
                'is_builtin': a.is_builtin,
                'order': a.order,
            }
            for a in attrs
        ]
        return Response(data)

    def post(self, request, slug):
        project = self.get_project()
        name = request.data.get('name', '').strip()
        field_type = request.data.get('field_type', 'text')
        options = request.data.get('options', [])

        if not name:
            return Response({'detail': _('Name is required.')}, status=status.HTTP_400_BAD_REQUEST)

        valid_types = dict(ProjectAttribute.FIELD_TYPE_CHOICES)
        if field_type not in valid_types:
            return Response({'detail': _('Invalid field type: %(type)s') % {'type': field_type}}, status=status.HTTP_400_BAD_REQUEST)

        if project.attributes.filter(name=name).exists():
            return Response({'detail': _('Attribute "%(name)s" already exists.') % {'name': name}}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(options, list):
            options = [o.strip() for o in str(options).split(',') if o.strip()]

        max_order = project.attributes.aggregate(models.Max('order'))['order__max']
        new_order = (max_order + 1) if max_order is not None else 0

        attr = ProjectAttribute.objects.create(
            project=project,
            name=name,
            field_type=field_type,
            options=options,
            order=new_order,
        )
        return Response({
            'id': attr.pk,
            'public_key': str(attr.public_key),
            'name': attr.name,
            'field_type': attr.field_type,
            'options': attr.options,
            'is_builtin': attr.is_builtin,
            'order': attr.order,
        }, status=status.HTTP_201_CREATED)


class ProjectAttributeUpdateDeleteView(ProjectAPIMixin, APIView):
    permission_classes = [IsAuthenticated, IsProjectEditorOrAdmin, ProjectNotArchived]

    def patch(self, request, slug, public_key):
        project = self.get_project()
        attr = get_object_or_404(ProjectAttribute, public_key=public_key, project=project)

        if attr.is_builtin:
            return Response({'detail': _('Cannot modify built-in attributes.')}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get('name')
        if name is not None:
            name = name.strip()
            if not name:
                return Response({'detail': _('Name is required.')}, status=status.HTTP_400_BAD_REQUEST)
            if project.attributes.filter(name=name).exclude(pk=attr.pk).exists():
                return Response({'detail': _('Attribute "%(name)s" already exists.') % {'name': name}}, status=status.HTTP_400_BAD_REQUEST)
            attr.name = name

        field_type = request.data.get('field_type')
        if field_type is not None:
            valid_types = dict(ProjectAttribute.FIELD_TYPE_CHOICES)
            if field_type not in valid_types:
                return Response({'detail': _('Invalid field type: %(type)s') % {'type': field_type}}, status=status.HTTP_400_BAD_REQUEST)
            attr.field_type = field_type

        options = request.data.get('options')
        if options is not None:
            if not isinstance(options, list):
                options = [o.strip() for o in str(options).split(',') if o.strip()]
            attr.options = options

        attr.save()
        return Response({
            'id': attr.pk,
            'public_key': str(attr.public_key),
            'name': attr.name,
            'field_type': attr.field_type,
            'options': attr.options,
            'is_builtin': attr.is_builtin,
            'order': attr.order,
        })

    def delete(self, request, slug, public_key):
        project = self.get_project()
        attr = get_object_or_404(ProjectAttribute, public_key=public_key, project=project)

        if attr.is_builtin:
            return Response({'detail': _('Cannot delete built-in attributes.')}, status=status.HTTP_400_BAD_REQUEST)

        attr.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
