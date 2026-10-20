from allauth.socialaccount.models import SocialAccount
from django import forms

from apps.accounts.captcha import CaptchaFormMixin
from apps.accounts.models import User, UserSettings


class LoginForm(CaptchaFormMixin, forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'username', 'autofocus': True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'current-password'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.password_first = bool(self.initial.get('email'))
        if self.password_first:
            del self.fields['email'].widget.attrs['autofocus']


class EmailForm(CaptchaFormMixin, forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email', 'autofocus': True})
    )


def microsoft_account_linked(user):
    return user.pk is not None and SocialAccount.objects.filter(user=user, provider='microsoft').exists()


class EditProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'display_name', 'department', 'location', 'phone']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance
        self.microsoft_linked = microsoft_account_linked(user)
        self.names_managed = self.microsoft_linked and bool(user.first_name and user.last_name)
        for name in ('first_name', 'last_name'):
            self.fields[name].required = not self.microsoft_linked
            self.fields[name].disabled = self.names_managed


class NotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = [
            'notify_project_updates', 'notify_comments', 'notify_status_changes',
            'notify_collaborator_changes', 'notify_weekly_digest',
        ]


class ExportDefaultsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = [
            'export_paper_size', 'export_orientation',
            'export_include_toc', 'export_include_attributes', 'export_include_comments',
            'export_include_links',
        ]
