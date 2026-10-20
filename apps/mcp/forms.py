from django import forms
from django.utils.translation import gettext_lazy as _
from oauth2_provider.forms import AllowForm


class ConsentForm(AllowForm):
    scope = forms.ChoiceField(
        choices=[('read', _('Read only')), ('read write', _('Read and write'))],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )
