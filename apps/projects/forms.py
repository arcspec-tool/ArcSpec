from django import forms
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.doctemplates.models import Template
from apps.projects.models import Project, Section


COLOR_CHOICES = [
    ('#284E8A', '#284E8A'),
    ('#7c3aed', '#7c3aed'),
    ('#198754', '#198754'),
    ('#ea580c', '#ea580c'),
    ('#0dcaf0', '#0dcaf0'),
    ('#dc3545', '#dc3545'),
]


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'template', 'status', 'color']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': gettext_lazy('e.g. Payment Gateway SRS'),
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': gettext_lazy('Brief description of the project...'),
            }),
            'template': forms.Select(attrs={
                'class': 'form-select',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'color': forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['template'].queryset = Template.objects.visible_to(user)
        self.fields['description'].required = False


class ProjectUpdateForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'status', 'color']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'color': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False


class SectionForm(forms.Form):
    title = forms.CharField(max_length=200, min_length=1)
    parent_id = forms.IntegerField(required=False)

    def __init__(self, *args, project=None, exclude_section=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.exclude_section = exclude_section

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError(_('Title is required.'))
        return title

    def clean_parent_id(self):
        parent_id = self.cleaned_data.get('parent_id')
        if parent_id is None:
            return None
        if self.exclude_section and parent_id == self.exclude_section.pk:
            raise forms.ValidationError(_('A section cannot be its own parent.'))
        if self.project:
            if not Section.objects.filter(pk=parent_id, project=self.project).exists():
                raise forms.ValidationError(_('Parent section does not belong to this project.'))
        return parent_id
