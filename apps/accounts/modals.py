from django.urls import reverse

from apps.accounts.forms import EditProfileForm
from apps.core.modals import register


def edit_profile_context(user, form=None):
    return {'form': form or EditProfileForm(instance=user), 'form_action': reverse('profile')}


@register('edit_profile', 'accounts/modals/_edit_profile.html', modal_id='editProfileModal')
def edit_profile(request, params):
    return edit_profile_context(request.user)
