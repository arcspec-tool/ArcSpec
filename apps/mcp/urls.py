from django.urls import include, path

from apps.mcp import views

urlpatterns = [
    path('', include('apps.mcp.oauth_urls')),
    path('settings/connected-apps/<uuid:public_key>/disconnect/', views.DisconnectView.as_view(), name='mcp_disconnect'),
]
