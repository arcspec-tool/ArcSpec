from django.urls import path

from apps.projects import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('activity-feed/', views.DashboardActivityFeedView.as_view(), name='dashboard_activity_feed'),
    path('notifications/', views.DashboardNotificationsView.as_view(), name='dashboard_notifications'),
]
