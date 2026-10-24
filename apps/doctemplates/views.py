from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

from apps.core.mixins import (
    LoginRequiredMixin,
    NotViewerMixin,
    TemplateOwnerOrAdminMixin,
    can_edit_template,
    visible_template,
)
from apps.core.modals import is_ajax, render_modal
from apps.doctemplates.forms import TemplateForm, TemplateImportForm
from apps.doctemplates.modals import attributes_from_post, editor_context, import_context, sections_from_post
from apps.doctemplates.models import Template, TemplateAttribute, TemplateSection
from apps.doctemplates.queries import template_list_queryset
from apps.doctemplates.transfer import file_content, file_name
from apps.doctemplates.writes import replace_attributes, replace_sections, save_template


class TemplateListView(LoginRequiredMixin, ListView):
    model = Template
    template_name = 'doctemplates/list.html'
    context_object_name = 'templates'

    def get_type(self):
        doc_type = self.request.GET.get('type', '').strip()
        return doc_type if doc_type in dict(Template.DOC_TYPE_CHOICES) else ''

    def get_queryset(self):
        return template_list_queryset(self.request.user, self.request.GET.get('q', '').strip(), self.get_type())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        templates = list(context['templates'])
        for tmpl in templates:
            tmpl.can_edit = can_edit_template(user, tmpl)
            tmpl.can_delete = tmpl.can_edit and tmpl.usage_count == 0
            tmpl.can_duplicate = not user.is_viewer
            tmpl.export_name = file_name(tmpl)
        context['builtin_templates'] = [t for t in templates if t.is_builtin]
        context['custom_templates'] = [t for t in templates if not t.is_builtin]

        counts = dict(
            Template.objects.visible_to(user).order_by().values_list('doc_type').annotate(n=Count('pk'))
        )
        context['type_filters'] = [('', _('All'), sum(counts.values()))] + [
            (value, label, counts.get(value, 0)) for value, label in Template.DOC_TYPE_CHOICES
        ]
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['selected_type'] = self.get_type()
        context['filters_active'] = bool(context['search_query'] or context['selected_type'])
        return context


def editor_error_response(request, form, template=None):
    if is_ajax(request):
        context = editor_context(
            template=template,
            form=form,
            sections=sections_from_post(request.POST),
            attributes=attributes_from_post(request.POST),
        )
        return render_modal(request, 'template_editor', context, status=422)
    messages.error(request, _('Please correct the errors below.'))
    return redirect('template_list')


class TemplateCreateView(NotViewerMixin, CreateView):
    model = Template
    form_class = TemplateForm
    success_url = reverse_lazy('template_list')

    @transaction.atomic
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.is_builtin = False
        self.object = form.save()
        _save_sections_from_post(self.request.POST, self.object)
        _save_attributes_from_post(self.request.POST, self.object)
        messages.success(self.request, _('Template "%(name)s" created.') % {'name': self.object.name})
        return redirect(self.success_url)

    def form_invalid(self, form):
        return editor_error_response(self.request, form)


class TemplateUpdateView(TemplateOwnerOrAdminMixin, UpdateView):
    model = Template
    form_class = TemplateForm
    success_url = reverse_lazy('template_list')

    def get_object(self, queryset=None):
        return self.template_obj

    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()
        _save_sections_from_post(self.request.POST, self.object)
        _save_attributes_from_post(self.request.POST, self.object)
        messages.success(self.request, _('Template "%(name)s" updated.') % {'name': self.object.name})
        return redirect(self.success_url)

    def form_invalid(self, form):
        return editor_error_response(self.request, form, self.template_obj)


def _save_sections_from_post(post_data, template):
    total = int(post_data.get('sections-TOTAL_FORMS', 0))
    if total == 0:
        return

    sections = []
    for i in range(total):
        prefix = f'sections-{i}-'
        title = post_data.get(prefix + 'title', '').strip()
        number = post_data.get(prefix + 'number', '').strip()
        description = post_data.get(prefix + 'description', '').strip()
        order = int(post_data.get(prefix + 'order', i))
        ref = post_data.get(prefix + 'ref', '').strip()
        parent_ref = post_data.get(prefix + 'parent_ref', '').strip()
        if not title:
            continue
        sections.append({
            'title': title,
            'number': number,
            'description': description,
            'order': order,
            'ref': ref,
            'parent_ref': parent_ref if parent_ref else None,
        })

    replace_sections(template, sections)


def _save_attributes_from_post(post_data, template):
    names = post_data.getlist('attr_name[]')
    types = post_data.getlist('attr_type[]')
    options_list = post_data.getlist('attr_options[]')

    valid_types = {'text', 'number', 'date', 'boolean', 'user', 'dropdown', 'multiselect'}

    attributes = []
    for i, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        field_type = types[i] if i < len(types) else 'text'
        if field_type not in valid_types:
            field_type = 'text'
        options = []
        if field_type in ('dropdown', 'multiselect') and i < len(options_list):
            options = [o.strip() for o in options_list[i].split(',') if o.strip()]
        attributes.append((name, field_type, options))
    replace_attributes(template, attributes)


class TemplateDeleteView(TemplateOwnerOrAdminMixin, DeleteView):
    model = Template
    success_url = reverse_lazy('template_list')

    def get_object(self, queryset=None):
        return self.template_obj

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.projects.exists():
            count = self.object.projects.count()
            messages.error(
                request,
                ngettext(
                    'Cannot delete "%(name)s": it is used by %(count)d project.',
                    'Cannot delete "%(name)s": it is used by %(count)d projects.',
                    count,
                ) % {'name': self.object.name, 'count': count},
            )
            return redirect(self.success_url)
        name = self.object.name
        self.object.delete()
        messages.success(request, _('Template "%(name)s" deleted.') % {'name': name})
        return redirect(self.success_url)


class TemplateDuplicateView(NotViewerMixin, View):

    def post(self, request, public_key):
        original = get_object_or_404(Template, public_key=public_key)
        if not original.is_builtin and not original.is_global and not request.user.is_system_admin:
            if original.created_by != request.user:
                raise PermissionDenied
        copy_name = _('%(name)s (Copy)') % {'name': original.name}
        new_template = Template.objects.create(
            name=copy_name,
            description=original.description,
            doc_type=original.doc_type,
            is_builtin=False,
            is_global=False,
            created_by=request.user,
        )
        old_to_new = {}
        for section in original.sections.order_by('order'):
            old_pk = section.pk
            new_section = TemplateSection.objects.create(
                template=new_template,
                title=section.title,
                description=section.description,
                number=section.number,
                order=section.order,
                parent=old_to_new.get(section.parent_id),
            )
            old_to_new[old_pk] = new_section

        for attr in original.attributes.order_by('order'):
            TemplateAttribute.objects.create(
                template=new_template,
                name=attr.name,
                field_type=attr.field_type,
                options=attr.options,
                is_builtin=attr.is_builtin,
                order=attr.order,
            )

        messages.success(request, _('Template duplicated as "%(name)s".') % {'name': copy_name})
        return redirect('template_list')


class TemplateExportView(LoginRequiredMixin, View):
    http_method_names = ['get']

    def get(self, request, public_key):
        template = visible_template(request.user, public_key)
        return HttpResponse(
            file_content(template),
            headers={
                'Content-Type': 'application/json',
                'Content-Disposition': f'attachment; filename="{file_name(template)}"',
            },
        )


class TemplateImportView(NotViewerMixin, FormView):
    form_class = TemplateImportForm
    http_method_names = ['post']

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'user': self.request.user}

    def form_valid(self, form):
        save_template(form.template, form.sections, form.attributes)
        messages.success(self.request, _('Template "%(name)s" imported.') % {'name': form.template.name})
        return redirect('template_list')

    def form_invalid(self, form):
        if is_ajax(self.request):
            return render_modal(self.request, 'template_import', import_context(form), status=422)
        for error in form.errors.get('file', []):
            messages.error(self.request, error)
        return redirect('template_list')

