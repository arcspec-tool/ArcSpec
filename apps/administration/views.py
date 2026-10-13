import logging
from smtplib import SMTPException

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.invitations import send_invitation
from apps.accounts.models import User
from apps.administration.forms import (
    EditRoleForm,
    InviteUserForm,
    SETTINGS_FORMS,
    TagPresetForm,
)
from apps.administration.modals import edit_role_context, invite_user_context, tag_preset_context
from apps.administration.models import SystemSettings
from apps.core.mixins import SystemAdminMixin
from apps.core.modals import is_ajax, render_modal
from apps.doctemplates.models import Template, TemplateSection
from apps.projects.models import Project, ProjectMembership, Tag

logger = logging.getLogger(__name__)

TABS = ('users', 'templates', 'tags', 'system')
ROLE_LABELS = dict(User.SYSTEM_ROLE_CHOICES)
ROLE_FILTERS = ('admin', 'user', 'viewer')


def panel_url(tab):
    return f'/admin-panel/?tab={tab}'


def count_per_user(queryset):
    counted = queryset.filter(user=OuterRef('pk')).order_by().values('user').annotate(n=Count('pk')).values('n')[:1]
    return Coalesce(Subquery(counted), 0)


def count_per_template(queryset):
    counted = queryset.filter(template=OuterRef('pk')).order_by().values('template').annotate(n=Count('pk')).values('n')[:1]
    return Coalesce(Subquery(counted), 0)


def can_resend_invitation(user):
    return user.is_active and not user.has_usable_password() and user.last_login is None


class AdminPanelView(SystemAdminMixin, TemplateView):
    template_name = 'administration/panel.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab = self.request.GET.get('tab', 'users')
        if tab not in TABS:
            tab = 'users'
        context['active_tab'] = tab
        context['tab_counts'] = {
            'users': User.objects.count(),
            'templates': Template.objects.count(),
            'tags': Tag.objects.filter(project__isnull=True).count(),
        }
        context.update(getattr(self, f'{tab}_context')())
        return context

    def users_context(self):
        users = User.objects.all()
        role_filter = self.request.GET.get('role', '')
        if role_filter not in ROLE_FILTERS:
            role_filter = ''
        user_search = self.request.GET.get('user_q', '').strip()

        user_list = users.annotate(project_count=count_per_user(ProjectMembership.objects.all()))
        if role_filter:
            user_list = user_list.filter(system_role=role_filter)
        if user_search:
            user_list = user_list.filter(
                Q(first_name__icontains=user_search)
                | Q(last_name__icontains=user_search)
                | Q(display_name__icontains=user_search)
                | Q(email__icontains=user_search)
            )
        user_list = list(user_list.order_by('-is_active', 'last_name', 'first_name', 'email'))
        for user in user_list:
            user.can_resend = can_resend_invitation(user)
            user.is_self = user.pk == self.request.user.pk

        role_counts = {row['system_role']: row['n'] for row in users.order_by().values('system_role').annotate(n=Count('pk'))}
        total_users = sum(role_counts.values())
        role_filters = [('', _('All'), total_users)] + [(role, ROLE_LABELS[role], role_counts.get(role, 0)) for role in ROLE_FILTERS]

        return {
            'total_users': total_users,
            'active_users': users.filter(is_active=True).count(),
            'admin_users': role_counts.get('admin', 0),
            'total_projects': Project.objects.count(),
            'user_list': user_list,
            'role_filter': role_filter,
            'role_filters': role_filters,
            'user_search': user_search,
            'filters_active': bool(role_filter or user_search),
        }

    def templates_context(self):
        return {
            'global_templates': Template.objects.select_related('created_by').annotate(
                usage_count=count_per_template(Project.objects.all()),
                section_total=count_per_template(TemplateSection.objects.all()),
            ).order_by('-is_builtin', 'display_order', 'name'),
        }

    def tags_context(self):
        return {
            'tag_presets': Tag.objects.filter(project__isnull=True).annotate(
                usage_count=Count('item_tags', distinct=True)
            ).order_by('name'),
        }

    def system_context(self):
        settings = SystemSettings.load()
        return {f'{name}_form': form_class(instance=settings) for name, form_class in SETTINGS_FORMS.items()}


def invite(request, user):
    try:
        send_invitation(request, user)
    except (OSError, SMTPException):
        logger.exception('The invitation email to %s could not be sent', user.email)
        messages.warning(request, _('The invitation email to %(email)s could not be sent. Use "Resend invitation" later.') % {'email': user.email})
    else:
        messages.success(request, _('Invitation sent to %(email)s.') % {'email': user.email})


class AdminInviteUserView(SystemAdminMixin, View):

    def post(self, request):
        form = InviteUserForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                email=form.cleaned_data['email'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                system_role='user',
                is_active=True,
            )
            user.set_unusable_password()
            user.save()
            invite(request, user)
            return redirect(panel_url('users'))
        if is_ajax(request):
            return render_modal(request, 'invite_user', invite_user_context(form), status=422)
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{error}')
        return redirect(panel_url('users'))


class AdminResendInvitationView(SystemAdminMixin, View):

    def post(self, request, public_key):
        user = get_object_or_404(User, public_key=public_key)
        if not user.is_active:
            messages.error(request, _('User "%(user)s" is deactivated. Reactivate the account before resending the invitation.') % {'user': user})
        elif user.has_usable_password():
            messages.error(request, _('User "%(user)s" already has a password. No invitation was sent.') % {'user': user})
        elif user.last_login is not None:
            messages.error(request, _('User "%(user)s" has already signed in. No invitation was sent.') % {'user': user})
        else:
            invite(request, user)
        return redirect(panel_url('users'))


class AdminEditRoleView(SystemAdminMixin, View):

    def post(self, request, public_key):
        user = get_object_or_404(User, public_key=public_key)
        if user == request.user:
            raise PermissionDenied
        form = EditRoleForm(request.POST)
        if form.is_valid():
            user.system_role = form.cleaned_data['system_role']
            user.save(update_fields=['system_role'])
            messages.success(request, _('Role for "%(user)s" updated to %(role)s.') % {'user': user, 'role': user.get_system_role_display()})
            return redirect(panel_url('users'))
        if is_ajax(request):
            return render_modal(request, 'edit_role', edit_role_context(user, form), status=422)
        return redirect(panel_url('users'))


class AdminDeactivateUserView(SystemAdminMixin, View):

    def post(self, request, public_key):
        user = get_object_or_404(User, public_key=public_key)
        if user == request.user:
            messages.error(request, _('You cannot deactivate yourself.'))
        else:
            user.is_active = not user.is_active
            user.save(update_fields=['is_active'])
            if user.is_active:
                messages.success(request, _('User "%(user)s" reactivated.') % {'user': user})
            else:
                messages.success(request, _('User "%(user)s" deactivated.') % {'user': user})
        return redirect(panel_url('users'))


class AdminTagPresetCreateView(SystemAdminMixin, View):

    def post(self, request):
        form = TagPresetForm(request.POST)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.project = None
            tag.is_preset = True
            tag.created_by = request.user
            tag.save()
            messages.success(request, _('Tag preset "%(name)s" created.') % {'name': tag.name})
            return redirect(panel_url('tags'))
        if is_ajax(request):
            return render_modal(request, 'tag_preset', tag_preset_context(form), status=422)
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{error}')
        return redirect(panel_url('tags'))


class AdminTagPresetDeleteView(SystemAdminMixin, View):

    def post(self, request, public_key):
        tag = get_object_or_404(Tag, public_key=public_key, project__isnull=True)
        name = tag.name
        tag.delete()
        messages.success(request, _('Tag preset "%(name)s" deleted.') % {'name': name})
        return redirect(panel_url('tags'))


class AdminTemplateToggleVisibilityView(SystemAdminMixin, View):

    def post(self, request, public_key):
        template = get_object_or_404(Template, public_key=public_key)
        if template.is_builtin:
            messages.error(request, _('Built-in templates are always visible and cannot be toggled.'))
        else:
            template.is_global = not template.is_global
            template.save(update_fields=['is_global'])
            if template.is_global:
                messages.success(request, _('Template "%(name)s" is now visible to all users.') % {'name': template.name})
            else:
                messages.success(request, _('Template "%(name)s" is now private.') % {'name': template.name})
        return redirect(panel_url('templates'))


class AdminSystemSettingsView(SystemAdminMixin, View):

    def post(self, request):
        form_class = SETTINGS_FORMS.get(request.POST.get('form_type'))
        if form_class is None:
            messages.error(request, _('Invalid form type.'))
            return redirect(panel_url('system'))
        form = form_class(request.POST, instance=SystemSettings.load())
        if form.is_valid():
            form.save()
            messages.success(request, _('System settings saved.'))
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
        return redirect(panel_url('system'))
