from django.urls import include, path

urlpatterns = [
    path('', include('apps.mcp.oauth_urls')),
]
