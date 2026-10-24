from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.doctemplates.models import Template, TemplateSection
from apps.doctemplates.transfer import template_from_file
from apps.doctemplates.writes import duplicate_attribute_names
from apps.projects.uploads import ANY_TEXT, check_content, extension

MEGABYTE = 1024 * 1024
MAX_IMPORT_SIZE = MEGABYTE
IMPORT_TYPES = ('application/json', ANY_TEXT)


class TemplateForm(forms.ModelForm):
    class Meta:
        model = Template
        fields = ['name', 'description', 'doc_type', 'is_global']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': gettext_lazy('e.g. Risk Analysis Template'),
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': gettext_lazy('Describe what this template is for...'),
            }),
            'doc_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'is_global': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'is_global': gettext_lazy('Visible to all users'),
        }

    def clean(self):
        cleaned_data = super().clean()
        names = [name.strip() for name in self.data.getlist('attr_name[]') if name.strip()]
        duplicates = duplicate_attribute_names(self.instance, names)
        if duplicates:
            raise forms.ValidationError(_('Attribute names must be unique: %(names)s.') % {'names': ', '.join(duplicates)})
        return cleaned_data


class TemplateImportForm(forms.Form):
    file = forms.FileField(
        label=gettext_lazy('Template file'),
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.json,application/json'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_file(self):
        uploaded = self.cleaned_data['file']
        if extension(uploaded.name) != '.json':
            raise ValidationError(_('The file must be a .json file.'))
        if uploaded.size > MAX_IMPORT_SIZE:
            raise ValidationError(_('The file is larger than %(count)d MB.') % {'count': MAX_IMPORT_SIZE // MEGABYTE})
        check_content(uploaded, IMPORT_TYPES)
        try:
            self.template, self.sections, self.attributes = template_from_file(uploaded.read(), self.user)
        except ValidationError as error:
            raise ValidationError(error.messages) from None
        return uploaded


class TemplateSectionForm(forms.ModelForm):
    class Meta:
        model = TemplateSection
        fields = ['title', 'description', 'number', 'order', 'parent']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'rows': 2,
                'placeholder': gettext_lazy('Describe this section...'),
            }),
            'number': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'order': forms.HiddenInput(),
            'parent': forms.HiddenInput(),
        }


TemplateSectionFormSet = inlineformset_factory(
    Template,
    TemplateSection,
    form=TemplateSectionForm,
    extra=0,
    can_delete=True,
)
