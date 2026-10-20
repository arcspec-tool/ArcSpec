from urllib.parse import urlencode, urlsplit

from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import resolve_url
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.exceptions import OAuthToolkitError
from oauth2_provider.settings import oauth2_settings
from oauth2_provider.views import (
    AuthorizationView, OAuthProtectedResourceMetadataView, OAuthServerMetadataView, RevokeTokenView, TokenView,
)
from oauthlib.oauth2.rfc6749.errors import CustomOAuth2Error

from apps.mcp import auth
from apps.mcp.forms import ConsentForm


class SwitchMixin:

    def dispatch(self, request, *args, **kwargs):
        if not auth.mcp_enabled():
            raise Http404
        response = super().dispatch(request, *args, **kwargs)
        response.setdefault('Cache-Control', 'no-store')
        return response


class ServerMetadataView(SwitchMixin, OAuthServerMetadataView):
    pass


class ResourceMetadataView(SwitchMixin, OAuthProtectedResourceMetadataView):
    pass


@method_decorator(csrf_exempt, name='dispatch')
class TokenEndpointView(SwitchMixin, TokenView):
    pass


@method_decorator(csrf_exempt, name='dispatch')
class RevocationView(SwitchMixin, RevokeTokenView):
    pass


class ConsentView(SwitchMixin, AuthorizationView):
    template_name = 'mcp/authorize.html'
    form_class = ConsentForm

    def handle_no_permission(self):
        return redirect_to_login(self.request.get_full_path(), resolve_url(self.get_login_url()), self.get_redirect_field_name())

    def get(self, request, *args, **kwargs):
        request.GET = request.GET.copy()
        request.GET.pop('approval_prompt', None)
        resources = request.GET.getlist('resource')
        if len(resources) != 1 or not auth.same_resource(resources[0], auth.resource_url()):
            return self.refuse_target(request)
        return super().get(request, *args, **kwargs)

    def refuse_target(self, request):
        try:
            scopes, credentials = self.validate_authorization_request(request)
        except OAuthToolkitError as error:
            return self.error_response(error, application=None)
        error = CustomOAuth2Error(
            error='invalid_target',
            description=_('The resource must be the MCP server of this site.'),
            state=credentials.get('state'),
        )
        return self.error_response(OAuthToolkitError(error=error, redirect_uri=credentials['redirect_uri']), application=None)

    def error_response(self, error, application, **kwargs):
        response = super().error_response(error, application, **kwargs)
        if response.status_code == 302:
            issuer = oauth2_settings.oauth2_authorization_server_issuer(self.request)
            response['Location'] += '&' + urlencode({'iss': issuer})
        return response

    def get_initial(self):
        initial = super().get_initial()
        initial['scope'] = 'read write' if 'write' in self.oauth2_data.get('scopes', []) else 'read'
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = context.get('application')
        if application is not None:
            context['client_name'] = application.name or _('Unnamed app')
            context['client_host'] = urlsplit(application.client_id).hostname
        return context
