from django.urls import path

from apps.mcp import views

app_name = 'oauth2_provider'

urlpatterns = [
    path('.well-known/oauth-authorization-server', views.ServerMetadataView.as_view(), name='oauth-server-metadata'),
    path('.well-known/oauth-protected-resource', views.ResourceMetadataView.as_view(), name='oauth-resource-metadata'),
    path('.well-known/oauth-protected-resource/mcp/', views.ResourceMetadataView.as_view(), name='oauth-resource-metadata-path'),
    path('oauth/authorize/', views.ConsentView.as_view(), name='authorize'),
    path('oauth/token/', views.TokenEndpointView.as_view(), name='token'),
    path('oauth/revoke/', views.RevocationView.as_view(), name='revoke-token'),
]
