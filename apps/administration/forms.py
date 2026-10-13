from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.auth_methods import entra_configured, validate
from apps.accounts.models import User
from apps.administration.models import SystemSettings
from apps.projects.models import Tag


class InviteUserForm(forms.Form):
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com', 'autocomplete': 'off'})
    )
    first_name = forms.CharField(
        label=_('First name'),
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('First name'), 'autocomplete': 'off'})
    )
    last_name = forms.CharField(
        label=_('Last name'),
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Last name'), 'autocomplete': 'off'})
    )

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('A user with this email already exists.'))
        return email


class EditRoleForm(forms.Form):
    system_role = forms.ChoiceField(
        choices=User.SYSTEM_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class TagPresetForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name', 'color']
        labels = {'name': _('Name'), 'color': _('Color')}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Tag name')}),
            'color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
        }


class SystemSettingsGeneralForm(forms.ModelForm):
    max_attachment_size_mb = forms.TypedChoiceField(
        coerce=int,
        choices=[(5, _('5 MB')), (10, _('10 MB')), (25, _('25 MB')), (50, _('50 MB'))],
        label=_('Max attachment size'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = SystemSettings
        fields = ['org_name', 'max_attachment_size_mb']
        labels = {'org_name': _('Organisation name')}
        widgets = {
            'org_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class BootstrapSwitchInput(forms.CheckboxInput):
    template_name = 'django/forms/widgets/input.html'


class SystemSettingsArchivingForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = [
            'auto_archive_enabled', 'auto_archive_days',
            'allow_user_restore',
            'auto_delete_archived', 'auto_delete_days',
        ]
        widgets = {
            'auto_archive_enabled': BootstrapSwitchInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'auto_archive_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'data-depends-on': 'id_auto_archive_enabled'}),
            'allow_user_restore': BootstrapSwitchInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'auto_delete_archived': BootstrapSwitchInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'auto_delete_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'data-depends-on': 'id_auto_delete_archived'}),
        }


class SystemSettingsAuthenticationForm(forms.ModelForm):
    both_off = _('At least one sign-in method must stay on.')

    class Meta:
        model = SystemSettings
        fields = ['entra_login_enabled', 'password_login_enabled']
        widgets = {
            'entra_login_enabled': BootstrapSwitchInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'password_login_enabled': BootstrapSwitchInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entra_configured = entra_configured()
        if not self.entra_configured:
            self.fields['entra_login_enabled'].widget.attrs['disabled'] = True
            self.initial['entra_login_enabled'] = False

    def clean(self):
        cleaned = super().clean()
        for error in validate(cleaned.get('entra_login_enabled', False), cleaned.get('password_login_enabled', False)):
            if error != str(self.both_off):
                self.add_error(None, error)
        return cleaned


SETTINGS_FORMS = {
    'general': SystemSettingsGeneralForm,
    'archiving': SystemSettingsArchivingForm,
    'authentication': SystemSettingsAuthenticationForm,
}
