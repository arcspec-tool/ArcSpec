from django.contrib.auth.mixins import LoginRequiredMixin as DjangoLoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

MEMBER_ROLES = ('admin', 'editor', 'viewer')
EDITOR_ROLES = ('admin', 'editor')
ADMIN_ROLES = ('admin',)


def require_system_admin(user):
    if not user.is_system_admin:
        raise PermissionDenied


def require_not_viewer(user):
    if user.is_viewer:
        raise PermissionDenied


def project_with_role(user, slug, roles=MEMBER_ROLES, writable=False):
    from apps.projects.models import Project
    project = get_object_or_404(Project, slug=slug)
    role = project.get_user_role(user)
    if role is None:
        raise Http404
    if role not in roles:
        raise PermissionDenied
    if writable and project.status == 'archived':
        raise PermissionDenied
    return project, role


def editable_template(user, public_key):
    from apps.doctemplates.models import Template
    template = get_object_or_404(Template, public_key=public_key)
    if template.is_builtin:
        raise PermissionDenied
    if not user.is_system_admin and template.created_by != user:
        raise PermissionDenied
    return template


def visible_template(user, public_key):
    from apps.doctemplates.models import Template
    template = get_object_or_404(Template, public_key=public_key)
    if not template.is_builtin and not template.is_global and not user.is_system_admin and template.created_by != user:
        raise PermissionDenied
    return template


class LoginRequiredMixin(DjangoLoginRequiredMixin):
    login_url = '/'


class SystemAdminMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        require_system_admin(request.user)
        return super().dispatch(request, *args, **kwargs)


class NotViewerMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        require_not_viewer(request.user)
        return super().dispatch(request, *args, **kwargs)


class ProjectMemberMixin(LoginRequiredMixin):
    required_roles = MEMBER_ROLES
    writable = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.project, self.user_role = project_with_role(
            request.user, self.kwargs.get('slug'), self.required_roles, self.writable,
        )
        return super().dispatch(request, *args, **kwargs)


class ProjectAdminMixin(ProjectMemberMixin):
    required_roles = ADMIN_ROLES


class ProjectEditorMixin(ProjectMemberMixin):
    required_roles = EDITOR_ROLES


class TemplateOwnerOrAdminMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.template_obj = editable_template(request.user, self.kwargs.get('public_key'))
        return super().dispatch(request, *args, **kwargs)
