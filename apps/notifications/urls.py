from django.urls import path

from apps.notifications import views

urlpatterns = [
    path('stream/', views.notification_stream, name='notification_stream'),
    path('<uuid:public_key>/read/', views.NotificationMarkReadView.as_view(), name='notification_mark_read'),
    path('read-all/', views.NotificationMarkAllReadView.as_view(), name='notification_mark_all_read'),
]
