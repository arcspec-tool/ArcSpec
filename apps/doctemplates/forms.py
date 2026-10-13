from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.doctemplates.models import Template, TemplateSection


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
        if self.instance.pk:
            names += self.instance.attributes.filter(is_builtin=True).values_list('name', flat=True)
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise forms.ValidationError(_('Attribute names must be unique: %(names)s.') % {'names': ', '.join(duplicates)})
        return cleaned_data


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
