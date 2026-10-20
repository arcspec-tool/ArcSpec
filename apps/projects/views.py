import json
import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseBadRequest, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.utils.http import http_date
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, ListView, TemplateView
from django.views.static import was_modified_since

from apps.administration.models import SystemSettings
from apps.core.mixins import LoginRequiredMixin, NotViewerMixin, ProjectAdminMixin, ProjectEditorMixin, ProjectMemberMixin
from apps.core.modals import is_ajax, render_modal
from apps.projects.modals import project_create_context, project_edit_context
from apps.notifications.models import AuditLog, Notification
from apps.projects.forms import ProjectForm, ProjectUpdateForm, SectionForm
from apps.projects.models import Attachment, Item, Project, ProjectAttribute, ProjectMembership, SavedView, Section, Tag
from apps.projects.queries import SORT_OPTIONS, attribute_rows, project_list_queryset, section_tree_with_counts
from apps.projects.utils import renumber_sections


DASHBOARD_FIRST_PAGE = 6
DASHBOARD_PAGE = 10


def dashboard_activity(user):
    project_ids = Project.objects.for_user(user).values_list('pk', flat=True)
    return AuditLog.objects.filter(project__in=project_ids).select_related('user', 'project').order_by('-created_at', '-pk')


def dashboard_notifications(user):
    return Notification.objects.filter(user=user).order_by('is_read', '-created_at', '-public_key')


def notification_cursor(notification):
    return {
        'read': int(notification.is_read),
        'before': notification.created_at.isoformat(),
        'key': str(notification.public_key),
    }


def parse_notification_cursor(params):
    read = params.get('read')
    if read not in ('0', '1'):
        return None
    try:
        before = parse_datetime(params.get('before', ''))
        key = uuid.UUID(params.get('key', ''))
    except ValueError:
        return None
    if before is None or before.tzinfo is None:
        return None
    return read == '1', before, key


def notifications_after(queryset, is_read, before, key):
    later = Q(is_read=is_read) & (Q(created_at__lt=before) | Q(created_at=before, public_key__lt=key))
    if is_read:
        return queryset.filter(later)
    return queryset.filter(later | Q(is_read=True))


def first_page(queryset):
    rows = list(queryset[:DASHBOARD_FIRST_PAGE + 1])
    return rows[:DASHBOARD_FIRST_PAGE], len(rows) > DASHBOARD_FIRST_PAGE


def next_page(queryset):
    rows = list(queryset[:DASHBOARD_PAGE + 1])
    return rows[:DASHBOARD_PAGE], len(rows) > DASHBOARD_PAGE


@method_decorator(ensure_csrf_cookie, name='dispatch')
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'projects/dashboard.html'

    def get_user_projects(self):
        return Project.objects.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        user_projects = self.get_user_projects()
        user_project_ids = user_projects.values_list('pk', flat=True)

        context['active_projects_count'] = user_projects.filter(status='active').count()
        context['approved_items_count'] = Item.objects.filter(
            project__in=user_project_ids, status='approved'
        ).count()
        context['in_review_items_count'] = Item.objects.filter(
            project__in=user_project_ids, status='in-review'
        ).count()
        context['collaborators_count'] = (
            ProjectMembership.objects.filter(project__in=user_project_ids)
            .exclude(user=user)
            .values('user')
            .distinct()
            .count()
        )

        context['recent_projects'] = user_projects.select_related('template', 'created_by')[:DASHBOARD_FIRST_PAGE]

        until = timezone.now()
        context['activity_until'] = until.isoformat()
        context['activity_feed'], context['activity_has_more'] = first_page(
            dashboard_activity(user).filter(created_at__lte=until)
        )

        notifications, context['notifications_has_more'] = first_page(dashboard_notifications(user))
        context['notifications'] = notifications
        if notifications:
            context['notifications_cursor'] = notification_cursor(notifications[-1])

        return context


def activity_feed_response(request, activities, hide_actor=False):
    try:
        offset = int(request.GET.get('offset', '0'))
    except ValueError:
        return HttpResponseBadRequest()
    if offset < 0:
        return HttpResponseBadRequest()

    until = request.GET.get('until')
    if until:
        try:
            until = parse_datetime(until)
        except ValueError:
            until = None
        if until is None or until.tzinfo is None:
            return HttpResponseBadRequest()
        activities = activities.filter(created_at__lte=until)

    rows, has_more = next_page(activities[offset:])
    html = render_to_string('projects/includes/_dashboard_activity.html', {'activities': rows, 'hide_actor': hide_actor}, request=request)
    return JsonResponse({'html': html, 'has_more': has_more})


class DashboardActivityFeedView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        return activity_feed_response(request, dashboard_activity(request.user))


class DashboardNotificationsView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        cursor = parse_notification_cursor(request.GET)
        if cursor is None:
            return HttpResponseBadRequest()

        rows, has_more = next_page(notifications_after(dashboard_notifications(request.user), *cursor))
        html = render_to_string('projects/includes/_dashboard_notifications.html', {'notifications': rows}, request=request)
        data = {'html': html, 'has_more': has_more}
        if rows:
            data['cursor'] = notification_cursor(rows[-1])
        return JsonResponse(data)


STATUS_FILTERS = ('active', 'in-review', 'draft', 'archived')
VIEW_MODES = ('grid', 'table')
VIEW_COOKIE = 'projects_view'


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'projects/list.html'
    context_object_name = 'projects'
    paginate_by = 12

    def get_status(self):
        status = self.request.GET.get('status', '')
        return status if status in STATUS_FILTERS else 'all'

    def get_sort(self):
        sort = self.request.GET.get('sort', 'updated')
        return sort if sort in SORT_OPTIONS else 'updated'

    def get_view_mode(self):
        view = self.request.GET.get('view')
        if view in VIEW_MODES:
            return view
        view = self.request.COOKIES.get(VIEW_COOKIE)
        return view if view in VIEW_MODES else 'grid'

    def get_queryset(self):
        return project_list_queryset(
            self.request.user, self.get_status(), self.request.GET.get('q', '').strip(), self.get_sort(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        projects = list(context['projects'])
        restore_allowed = user.is_system_admin or SystemSettings.load().allow_user_restore
        for project in projects:
            archived = project.status == 'archived'
            project.can_manage = project.user_role == 'admin'
            project.can_restore = archived and project.can_manage and restore_allowed
            project.can_duplicate = not archived and not user.is_viewer and project.user_role in ('admin', 'editor')
        context['projects'] = projects

        counts = {}
        for row in Project.objects.for_user(user).order_by().values('status').annotate(n=Count('pk', distinct=True)):
            counts[row['status']] = counts.get(row['status'], 0) + row['n']
        context['status_counts'] = counts
        context['total_count'] = sum(counts.values())
        context['status_filters'] = [
            ('all', _('All'), context['total_count']),
            ('active', _('Active'), counts.get('active', 0)),
            ('in-review', _('In Review'), counts.get('in-review', 0)),
            ('draft', _('Draft'), counts.get('draft', 0)),
            ('archived', _('Archived'), counts.get('archived', 0)),
        ]

        context['active_status'] = self.get_status()
        context['active_sort'] = self.get_sort()
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['view_mode'] = self.get_view_mode()
        context['filters_active'] = bool(context['search_query']) or context['active_status'] != 'all'
        return context

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        view = self.request.GET.get('view')
        if view in VIEW_MODES:
            response.set_cookie(
                VIEW_COOKIE, view, max_age=365 * 24 * 3600, samesite='Lax',
                secure=self.request.is_secure(), httponly=True,
            )
        return response


class ProjectCreateView(NotViewerMixin, View):

    def post(self, request):
        form = ProjectForm(request.POST, user=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.slug = Project.generate_unique_slug(form.cleaned_data['name'])
            project.save()
            ProjectMembership.objects.create(
                project=project, user=request.user, role='admin', added_by=request.user
            )
            project.copy_template_structure()
            messages.success(request, _('Project "%(name)s" created.') % {'name': project.name})
            return redirect('project_list')
        if is_ajax(request):
            return render_modal(request, 'project_create', project_create_context(request, form), status=422)
        messages.error(request, _('Please correct the errors below.'))
        return redirect('project_list')


class ProjectUpdateView(ProjectAdminMixin, View):
    writable = True

    def post(self, request, slug):
        form = ProjectUpdateForm(request.POST, instance=self.project)
        if form.is_valid():
            project = form.save(commit=False)
            if 'status' in form.changed_data and project.status == 'archived':
                project.archived_at = timezone.now()
            project.save()
            messages.success(request, _('Project "%(name)s" updated.') % {'name': self.project.name})
            return redirect('project_list')
        if is_ajax(request):
            return render_modal(request, 'project_edit', project_edit_context(self.project, form), status=422)
        messages.error(request, _('Please correct the errors below.'))
        return redirect('project_list')


class ProjectArchiveView(ProjectAdminMixin, View):

    def post(self, request, slug):
        self.project.status = 'archived'
        self.project.archived_at = timezone.now()
        self.project.save()
        messages.success(request, _('Project "%(name)s" archived.') % {'name': self.project.name})
        return redirect('project_list')


class ProjectRestoreView(ProjectAdminMixin, View):

    def post(self, request, slug):
        if not request.user.is_system_admin and not SystemSettings.load().allow_user_restore:
            raise PermissionDenied
        self.project.status = 'active'
        self.project.archived_at = None
        self.project.save()
        messages.success(request, _('Project "%(name)s" restored.') % {'name': self.project.name})
        return redirect('project_list')


class ProjectDeleteView(ProjectAdminMixin, View):

    def post(self, request, slug):
        name = self.project.name
        self.project.delete()
        messages.success(request, _('Project "%(name)s" deleted.') % {'name': name})
        return redirect('project_list')


class ProjectDuplicateView(NotViewerMixin, ProjectEditorMixin, View):

    def post(self, request, slug):
        original = self.project
        copy_name = _('%(name)s (Copy)') % {'name': original.name}
        new_slug = Project.generate_unique_slug(copy_name)
        new_project = Project.objects.create(
            name=copy_name,
            slug=new_slug,
            description=original.description,
            template=original.template,
            status='draft',
            color=original.color,
            created_by=request.user,
            next_item_number=1,
        )
        ProjectMembership.objects.create(
            project=new_project, user=request.user, role='admin', added_by=request.user
        )
        old_to_new = {}
        for section in original.sections.order_by('order'):
            new_section = Section.objects.create(
                project=new_project,
                title=section.title,
                description=section.description,
                number=section.number,
                order=section.order,
                parent=old_to_new.get(section.parent_id),
            )
            old_to_new[section.pk] = new_section
        attr_old_to_new = {}
        for attr in original.attributes.order_by('order'):
            new_attr = ProjectAttribute.objects.create(
                project=new_project,
                name=attr.name,
                field_type=attr.field_type,
                options=attr.options,
                is_builtin=attr.is_builtin,
                order=attr.order,
            )
            attr_old_to_new[attr.pk] = new_attr
        messages.success(request, _('Project duplicated as "%(name)s".') % {'name': copy_name})
        return redirect('project_list')


@method_decorator(ensure_csrf_cookie, name='dispatch')
class ProjectDetailView(ProjectMemberMixin, DetailView):
    model = Project
    template_name = 'projects/detail.html'
    context_object_name = 'project'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object

        sections, context['root_sections'], context['children_map'] = section_tree_with_counts(project)
        context['sections'] = sections

        items = list(Item.objects.filter(project=project).select_related(
            'section', 'assignee'
        ).prefetch_related('item_tags__tag').annotate(
            attachment_count=Count('attachments'),
            comment_count=Count('comments'),
        ).order_by('section__order', 'order'))
        context['items'] = items

        items_by_section = {}
        for item in items:
            items_by_section.setdefault(item.section_id, []).append(item)
        context['items_by_section'] = items_by_section

        status_counts = {}
        for item in items:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
        context['status_counts'] = status_counts
        context['status_summary'] = [
            {'value': value, 'label': label, 'count': status_counts[value]}
            for value, label in Item.STATUS_CHOICES if status_counts.get(value)
        ]
        context['total_items'] = len(items)

        memberships = ProjectMembership.objects.filter(
            project=project
        ).select_related('user')
        context['memberships'] = memberships

        context['project_tags'] = Tag.for_project(project)
        context['status_choices'] = Item.STATUS_CHOICES
        context['priority_choices'] = Item.PRIORITY_CHOICES

        archived = project.status == 'archived'
        context['user_role'] = self.user_role
        context['is_archived'] = archived
        context['is_editor'] = self.user_role in ('admin', 'editor') and not archived
        context['is_admin'] = self.user_role == 'admin' and not archived

        context['saved_views'] = list(SavedView.objects.filter(
            project=project, user=self.request.user
        ))
        context['deletable_views'] = [view for view in context['saved_views'] if not view.is_default]

        section_data = {}
        for section in sections:
            section_data[str(section.pk)] = {
                'title': section.title,
                'description': section.description,
                'number': section.number,
                'key': str(section.public_key),
                'total_items': getattr(section, 'total_items', 0),
            }
        context['section_data'] = section_data

        context['template_attributes'] = attribute_rows(project)

        return context


class ProjectExportView(ProjectMemberMixin, View):

    def post(self, request, slug):
        from apps.projects.export import export_project
        export_format = request.POST.get('format', 'pdf')
        export_attr_ids = request.POST.getlist('export_attr_ids')
        options = {
            'paper_size': request.POST.get('paper_size', 'a4'),
            'orientation': request.POST.get('orientation', 'portrait'),
            'include_toc': 'include_toc' in request.POST,
            'include_authors': 'include_authors' in request.POST,
            'include_assignee': 'include_assignee' in request.POST,
            'include_attributes': 'include_attributes' in request.POST,
            'export_attr_ids': [int(x) for x in export_attr_ids if x.isdigit()],
            'include_comments': 'include_comments' in request.POST,
            'include_links': 'include_links' in request.POST,
        }
        return export_project(self.project, export_format, options)


class AttachmentDownloadView(ProjectMemberMixin, View):

    def get(self, request, slug, public_key):
        attachment = get_object_or_404(
            Attachment, public_key=public_key, item__project=self.project
        )
        if not attachment.file:
            raise Http404
        return FileResponse(
            attachment.file.open('rb'),
            as_attachment=True,
            filename=attachment.filename,
        )


class ItemImageView(ProjectMemberMixin, View):

    def get(self, request, slug, public_key):
        item = get_object_or_404(Item, public_key=public_key, project=self.project)
        if not item.image:
            raise Http404
        storage, name = item.image.storage, item.image.name
        if not storage.exists(name):
            raise Http404
        modified = storage.get_modified_time(name).timestamp()
        if was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'), modified):
            response = FileResponse(storage.open(name, 'rb'))
            response['Last-Modified'] = http_date(modified)
        else:
            response = HttpResponseNotModified()
        response['Cache-Control'] = 'private, no-cache'
        return response


def _section_to_dict(section):
    return {
        'id': section.pk,
        'public_key': str(section.public_key),
        'title': section.title,
        'description': section.description,
        'number': section.number,
        'order': section.order,
        'parent_id': section.parent_id,
    }


def _parse_json_body(request):
    import json
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


class SectionCreateView(ProjectEditorMixin, View):
    writable = True

    def post(self, request, slug):
        data = _parse_json_body(request)
        form = SectionForm(data, project=self.project)
        if not form.is_valid():
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

        parent_id = form.cleaned_data['parent_id']
        siblings = Section.objects.filter(project=self.project, parent_id=parent_id)
        max_order = siblings.aggregate(models.Max('order'))['order__max']
        new_order = (max_order + 1) if max_order is not None else 0

        description = data.get('description', '').strip() if isinstance(data, dict) else ''
        section = Section(
            project=self.project,
            title=form.cleaned_data['title'],
            description=description,
            parent_id=parent_id,
            order=new_order,
            number='',
        )
        section._actor = request.user
        section.save()
        renumber_sections(self.project, request.user)
        section.refresh_from_db()
        return JsonResponse({'ok': True, 'section': _section_to_dict(section)})


def _would_create_cycle(section_pk, new_parent_id):
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == section_pk:
            return True
        if current in visited:
            return True
        visited.add(current)
        current = Section.objects.filter(pk=current).values_list('parent_id', flat=True).first()
    return False


class SectionUpdateView(ProjectEditorMixin, View):
    writable = True

    def post(self, request, slug, public_key):
        section = get_object_or_404(Section, public_key=public_key, project=self.project)
        data = _parse_json_body(request)
        form = SectionForm(data, project=self.project, exclude_section=section)

        title = data.get('title')
        if title is not None:
            if not title.strip():
                return JsonResponse(
                    {'ok': False, 'errors': {'title': [_('Title is required.')]}},
                    status=400,
                )
            section.title = title.strip()

        if 'description' in data:
            section.description = data.get('description', '').strip()

        if 'parent_id' in data:
            parent_id = data.get('parent_id')
            if parent_id is not None:
                if parent_id == section.pk:
                    return JsonResponse(
                        {'ok': False, 'errors': {'parent_id': [_('A section cannot be its own parent.')]}},
                        status=400,
                    )
                if not Section.objects.filter(pk=parent_id, project=self.project).exists():
                    return JsonResponse(
                        {'ok': False, 'errors': {'parent_id': [_('Parent section does not belong to this project.')]}},
                        status=400,
                    )
                if _would_create_cycle(section.pk, parent_id):
                    return JsonResponse(
                        {'ok': False, 'errors': {'parent_id': [_('This move would create a circular hierarchy.')]}},
                        status=400,
                    )
            section.parent_id = parent_id

        section._actor = request.user
        section.save()
        renumber_sections(self.project, request.user)
        section.refresh_from_db()
        return JsonResponse({'ok': True, 'section': _section_to_dict(section)})


def _section_has_items_recursive(section, _visited=None):
    if _visited is None:
        _visited = set()
    if section.pk in _visited:
        return False
    _visited.add(section.pk)
    if section.items.exists():
        return True
    for child in section.children.all():
        if _section_has_items_recursive(child, _visited):
            return True
    return False


class SectionDeleteView(ProjectEditorMixin, View):
    writable = True

    def post(self, request, slug, public_key):
        section = get_object_or_404(Section, public_key=public_key, project=self.project)

        if _section_has_items_recursive(section):
            return JsonResponse({
                'ok': False,
                'error': _('Cannot delete section that contains items. Move or delete items first.'),
            }, status=400)

        section._actor = request.user
        section.delete()
        renumber_sections(self.project, request.user)
        return JsonResponse({'ok': True})


class SectionReorderView(ProjectEditorMixin, View):
    writable = True

    def post(self, request, slug):
        data = _parse_json_body(request)
        order_list = data.get('order', [])

        section_ids = [entry['id'] for entry in order_list]
        project_section_ids = set(
            Section.objects.filter(project=self.project).values_list('pk', flat=True)
        )
        if not set(section_ids).issubset(project_section_ids):
            return JsonResponse({
                'ok': False,
                'error': _('One or more sections do not belong to this project.'),
            }, status=400)

        proposed_parents = {entry['id']: entry.get('parent_id') for entry in order_list}
        for section_id, parent_id in proposed_parents.items():
            if parent_id is None:
                continue
            visited = set()
            current = parent_id
            while current is not None:
                if current == section_id:
                    return JsonResponse({
                        'ok': False,
                        'error': _('This reorder would create a circular hierarchy.'),
                    }, status=400)
                if current in visited:
                    break
                visited.add(current)
                current = proposed_parents.get(current)

        for i, entry in enumerate(order_list):
            Section.objects.filter(pk=entry['id'], project=self.project).update(
                order=i,
                parent_id=entry.get('parent_id'),
            )

        renumber_sections(self.project, request.user)
        return JsonResponse({'ok': True})
