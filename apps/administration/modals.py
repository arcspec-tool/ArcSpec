from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import reverse

from apps.accounts.models import User
from apps.administration.forms import EditRoleForm, InviteUserForm, TagPresetForm
from apps.core.mixins import require_system_admin
from apps.core.modals import key_param, register


def invite_user_context(form=None):
    return {'form': form or InviteUserForm(), 'form_action': reverse('admin_invite_user')}


def edit_role_context(user, form=None):
    return {
        'edited_user': user,
        'form': form or EditRoleForm(initial={'system_role': user.system_role}),
        'form_action': reverse('admin_edit_role', args=[user.public_key]),
    }


def tag_preset_context(form=None):
    return {'form': form or TagPresetForm(), 'form_action': reverse('admin_tag_preset_create')}


@register('invite_user', 'administration/modals/_invite_user.html', modal_id='inviteUserModal')
def invite_user(request, params):
    require_system_admin(request.user)
    return invite_user_context()


@register('edit_role', 'administration/modals/_edit_role.html', params=('user',), modal_id='editRoleModal', size='sm')
def edit_role(request, params):
    require_system_admin(request.user)
    user = get_object_or_404(User, public_key=key_param(params, 'user'))
    if user == request.user:
        raise PermissionDenied
    return edit_role_context(user)


@register('tag_preset', 'administration/modals/_tag_preset.html', modal_id='tagPresetModal', size='sm')
def tag_preset(request, params):
    require_system_admin(request.user)
    return tag_preset_context()
