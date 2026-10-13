from django.urls import path

from apps.doctemplates import views

urlpatterns = [
    path('', views.TemplateListView.as_view(), name='template_list'),
    path('create/', views.TemplateCreateView.as_view(), name='template_create'),
    path('<uuid:public_key>/edit/', views.TemplateUpdateView.as_view(), name='template_edit'),
    path('<uuid:public_key>/delete/', views.TemplateDeleteView.as_view(), name='template_delete'),
    path('<uuid:public_key>/duplicate/', views.TemplateDuplicateView.as_view(), name='template_duplicate'),
]
