from allauth.socialaccount.providers.microsoft.views import oauth2_callback
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.utils import timezone
from django.views.decorators.http import last_modified
from django.views.i18n import JavaScriptCatalog

from apps.accounts.views import entra_login
from apps.core.views import ModalView, health

callback_prefix = f'auth/callback/{settings.AUTH_CALLBACK_PREFIX}/'
catalog_modified = timezone.now()

urlpatterns = [
    path('health/', health, name='health'),
    path('jsi18n/', last_modified(lambda request, **kwargs: catalog_modified)(JavaScriptCatalog.as_view()), name='javascript-catalog'),
    path('modals/<slug:name>/', ModalView.as_view(), name='modal'),
    path('', include('apps.accounts.urls')),
    path('', include('apps.mcp.urls')),
    path('dashboard/', include(('apps.projects.urls_dashboard', 'dashboard'))),
    path('projects/', include('apps.projects.urls')),
    path('templates/', include('apps.doctemplates.urls')),
    path('admin-panel/', include('apps.administration.urls')),
    path('api/projects/', include('apps.projects.urls_api')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('auth/microsoft/', entra_login, name='microsoft_login'),
    path(f'{callback_prefix}microsoft/login/callback/', oauth2_callback, name='microsoft_callback'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
