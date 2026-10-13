import logging
from functools import cache
from smtplib import SMTPException

from allauth.socialaccount.providers.microsoft.views import oauth2_login
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View
from django.views.generic import TemplateView, UpdateView

from apps.accounts.auth_methods import current
from apps.accounts.emails import link_days, send_password_link_email
from apps.accounts.forms import EditProfileForm, EmailForm, ExportDefaultsForm, LoginForm, NotificationSettingsForm, microsoft_account_linked
from apps.accounts.modals import edit_profile_context
from apps.accounts.models import User, UserSettings
from apps.accounts.throttles import (
    ForgotAddressThrottle,
    ForgotEmailThrottle,
    LoginAddressThrottle,
    LoginEmailThrottle,
    throttled,
)
from apps.accounts.tokens import make_link, user_from_link
from apps.core.mixins import LoginRequiredMixin
from apps.projects.views import activity_feed_response, first_page
from apps.core.modals import is_ajax, render_modal
from apps.notifications.models import AuditLog
from apps.projects.models import Comment, Item, Project, ProjectMembership

logger = logging.getLogger(__name__)


@cache
def dummy_hash():
    return make_password('never-compared-against-a-real-password')


def password_login_off(request):
    messages.error(request, _('Password sign-in is turned off.'))
    return redirect('/')


def entra_login(request):
    if not current().entra:
        messages.error(request, _('Microsoft sign-in is turned off.'))
        return redirect('/')
    return oauth2_login(request)


class LoginView(TemplateView):
    template_name = 'accounts/login.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', LoginForm())
        context['next'] = self.request.POST.get('next') or self.request.GET.get('next', '')
        return context

    def post(self, request, *args, **kwargs):
        if not current().password:
            return password_login_off(request)
        form = LoginForm(request.POST)
        email = form.data.get('email', '').strip()
        if throttled(request, LoginAddressThrottle, LoginEmailThrottle):
            messages.error(request, _('Too many attempts. Try again in a few minutes.'))
            return self.render_to_response(self.get_context_data(form=LoginForm(initial={'email': email})))
        password = form.data.get('password', '')
        user = self.authenticate(email if form.is_valid() else '', password)
        if user is None:
            logger.info('Sign-in failed for %s from %s', email, request.META.get('REMOTE_ADDR'))
            messages.error(request, _('Incorrect email address or password.'))
            return self.render_to_response(self.get_context_data(form=LoginForm(initial={'email': email})))
        if not user.is_active:
            logger.info('Sign-in refused for deactivated %s from %s', email, request.META.get('REMOTE_ADDR'))
            messages.error(request, _('Your account has been deactivated. Contact a system administrator.'))
            return self.render_to_response(self.get_context_data(form=LoginForm(initial={'email': email})))
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(self.safe_next(request) or settings.LOGIN_REDIRECT_URL)

    @staticmethod
    def authenticate(email, password):
        user = None
        if email:
            try:
                user = User.objects.get(email__iexact=email)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                user = None
        if user is None or not user.has_usable_password():
            check_password(password, dummy_hash())
            return None
        return user if user.check_password(password) else None

    @staticmethod
    def safe_next(request):
        target = request.POST.get('next', '')
        if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return target
        return ''


class LogoutView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect('/')


class ForgotPasswordView(TemplateView):
    template_name = 'accounts/forgot_password.html'

    def dispatch(self, request, *args, **kwargs):
        if not current().password:
            return password_login_off(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', EmailForm())
        return context

    def post(self, request, *args, **kwargs):
        form = EmailForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        if throttled(request, ForgotAddressThrottle, ForgotEmailThrottle):
            messages.error(request, _('Too many attempts. Try again in a few minutes.'))
            return self.render_to_response(self.get_context_data(form=form))
        email = form.cleaned_data['email']
        users = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
        if len(users) == 1:
            user = users[0]
            try:
                send_password_link_email(user, make_link(request, user))
            except (OSError, SMTPException):
                logger.exception('The password link email to %s could not be sent', email)
                messages.error(request, _('The email could not be sent. Try again later.'))
                return self.render_to_response(self.get_context_data(form=form))
        return render(request, 'accounts/forgot_sent.html', {'email': email, 'link_days': link_days()})


class SetPasswordView(TemplateView):
    template_name = 'accounts/set_password.html'

    def dispatch(self, request, public_key, token, *args, **kwargs):
        if not current().password:
            return password_login_off(request)
        self.user = user_from_link(public_key, token)
        if self.user is None:
            return render(request, 'accounts/set_password_invalid.html')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', SetPasswordForm(self.user))
        return context

    def post(self, request, *args, **kwargs):
        form = SetPasswordForm(self.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _('Password set. You can sign in now.'))
            return redirect('/')
        return self.render_to_response(self.get_context_data(form=form))


class ChangePasswordView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/change_password.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not current().password:
            return password_login_off(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_usable_password():
            context.setdefault('form', PasswordChangeForm(self.request.user))
        context['no_password_message'] = _('You have no password yet. Sign out, then use Forgot password on the sign-in page to set one.')
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.has_usable_password():
            return self.render_to_response(self.get_context_data())
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, _('Password changed.'))
            return redirect(reverse('settings') + '#account')
        return self.render_to_response(self.get_context_data(form=form))


def profile_activity(user):
    project_ids = ProjectMembership.objects.filter(user=user).values_list('project_id', flat=True)
    return AuditLog.objects.filter(user=user, project_id__in=project_ids).select_related('user', 'project').order_by('-created_at', '-pk')


class ProfileActivityFeedView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        return activity_feed_response(request, profile_activity(request.user), hide_actor=True)


class ProfileView(LoginRequiredMixin, UpdateView):
    template_name = 'accounts/profile.html'
    form_class = EditProfileForm
    context_object_name = 'profile_user'

    def get_object(self):
        return self.request.user

    def get_success_url(self):
        return reverse('profile')

    def form_valid(self, form):
        messages.success(self.request, _('Profile updated successfully.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        if is_ajax(self.request):
            return render_modal(self.request, 'edit_profile', edit_profile_context(self.request.user, form), status=422)
        messages.error(self.request, _('Please correct the errors below.'))
        return redirect('profile')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        item_total = Item.objects.filter(project=OuterRef('project')).order_by().values('project').annotate(n=Count('pk')).values('n')[:1]
        memberships = (
            ProjectMembership.objects.filter(user=user)
            .select_related('project')
            .annotate(items_total=Coalesce(Subquery(item_total), 0))
            .order_by('-project__updated_at')
        )
        projects = []
        for membership in memberships:
            membership.project.user_role = membership.role
            membership.project.items_total = membership.items_total
            projects.append(membership.project)
        projects.sort(key=lambda project: project.status == 'archived')
        context['assigned_projects'] = projects

        context['activity_stats'] = {
            'projects_count': len(projects),
            'items_created': Item.objects.filter(created_by=user).count(),
            'comments_count': Comment.objects.filter(author=user).count(),
        }

        until = timezone.now()
        context['activity_until'] = until.isoformat()
        context['recent_activity'], context['activity_has_more'] = first_page(
            profile_activity(user).filter(created_at__lte=until)
        )

        context['sign_in'] = {
            'microsoft': microsoft_account_linked(user),
            'password': user.has_usable_password(),
            'password_enabled': current().password,
        }
        return context


SETTINGS_FORMS = {
    'notifications': (NotificationSettingsForm, gettext_lazy('Email notification settings saved.')),
    'export': (ExportDefaultsForm, gettext_lazy('Export defaults saved.')),
}


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        user_settings = user.settings
        methods = current()
        context['notification_form'] = NotificationSettingsForm(instance=user_settings)
        context['export_form'] = ExportDefaultsForm(instance=user_settings)
        context['paper_sizes'] = UserSettings.PAPER_SIZE_CHOICES
        context['orientations'] = UserSettings.ORIENTATION_CHOICES
        context['sign_in'] = {
            'microsoft': microsoft_account_linked(user),
            'microsoft_enabled': methods.entra,
            'password': user.has_usable_password(),
            'password_enabled': methods.password,
        }
        return context

    def post(self, request, *args, **kwargs):
        form_type = request.POST.get('form_type')
        if form_type not in SETTINGS_FORMS:
            if is_ajax(request):
                return JsonResponse({'status': 'error'}, status=400)
            return self.render_to_response(self.get_context_data())
        form_class, message = SETTINGS_FORMS[form_type]
        form = form_class(request.POST, instance=request.user.settings)
        if not form.is_valid():
            if is_ajax(request):
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            return self.render_to_response(self.get_context_data())
        form.save()
        if is_ajax(request):
            return JsonResponse({'status': 'ok', 'message': message})
        messages.success(request, message)
        return redirect(reverse('settings') + '#' + form_type)
