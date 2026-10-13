from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.projects.models import Project


class ProjectPermissionBase(BasePermission):

    def _get_project(self, view):
        slug = view.kwargs.get('slug')
        if slug:
            try:
                return Project.objects.get(slug=slug)
            except Project.DoesNotExist:
                return None
        return getattr(view, 'project', None)

    def _get_role(self, request, project):
        if not project:
            return None
        return project.get_user_role(request.user)

    def _check_membership_or_404(self, request, view):
        project = self._get_project(view)
        if not project:
            raise NotFound
        role = self._get_role(request, project)
        if role is None:
            raise NotFound
        return role


class ProjectRolePermission(ProjectPermissionBase):

    def __init__(self, allowed_roles=None):
        self.allowed_roles = allowed_roles or ['admin', 'editor', 'viewer']

    def has_permission(self, request, view):
        role = self._check_membership_or_404(request, view)
        return role in self.allowed_roles

    @classmethod
    def as_member(cls):
        return cls(allowed_roles=['admin', 'editor', 'viewer'])

    @classmethod
    def as_editor_or_admin(cls):
        return cls(allowed_roles=['admin', 'editor'])

    @classmethod
    def as_admin(cls):
        return cls(allowed_roles=['admin'])


class IsProjectMember(ProjectPermissionBase):

    def has_permission(self, request, view):
        self._check_membership_or_404(request, view)
        return True


class IsProjectEditorOrAdmin(ProjectPermissionBase):

    def has_permission(self, request, view):
        role = self._check_membership_or_404(request, view)
        return role in ('admin', 'editor')


class IsProjectAdmin(ProjectPermissionBase):

    def has_permission(self, request, view):
        role = self._check_membership_or_404(request, view)
        return role == 'admin'


class ProjectNotArchived(ProjectPermissionBase):
    message = _('This project is archived. Restore it to make changes.')

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        project = self._get_project(view)
        return project is not None and project.status != 'archived'
