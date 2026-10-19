from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.accounts.auth_methods import can_change_password
from apps.accounts.forms import EditProfileForm
from apps.core.modals import register

PASSWORD_FIELDS = ('old_password', 'new_password1', 'new_password2')
PASSWORD_ORIGINS = ('profile', 'settings')


def edit_profile_context(user, form=None):
    return {'form': form or EditProfileForm(instance=user), 'form_action': reverse('profile')}


@register('edit_profile', 'accounts/modals/_edit_profile.html', modal_id='editProfileModal')
def edit_profile(request, params):
    return edit_profile_context(request.user)


def password_origin(value):
    return value if value in PASSWORD_ORIGINS else 'profile'


def password_return_url(origin):
    return reverse('settings') + '#account' if origin == 'settings' else reverse('profile')


def change_password_context(user, form=None, origin='profile'):
    form = form or PasswordChangeForm(user)
    return {
        'form': form,
        'form_action': reverse('change_password'),
        'origin': origin,
        'focus': next((name for name in PASSWORD_FIELDS if name in form.errors), PASSWORD_FIELDS[0]),
    }


@register('change_password', 'accounts/modals/_change_password.html', params=('origin',), modal_id='changePasswordModal')
def change_password(request, params):
    if not can_change_password(request.user):
        raise PermissionDenied
    return change_password_context(request.user, origin=password_origin(params.get('origin')))
