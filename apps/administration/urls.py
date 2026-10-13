from django.urls import path

from apps.administration import views

urlpatterns = [
    path('', views.AdminPanelView.as_view(), name='admin_panel'),
    path('invite-user/', views.AdminInviteUserView.as_view(), name='admin_invite_user'),
    path('edit-role/<uuid:public_key>/', views.AdminEditRoleView.as_view(), name='admin_edit_role'),
    path('deactivate/<uuid:public_key>/', views.AdminDeactivateUserView.as_view(), name='admin_deactivate_user'),
    path('resend-invitation/<uuid:public_key>/', views.AdminResendInvitationView.as_view(), name='admin_resend_invitation'),
    path('tag-preset/create/', views.AdminTagPresetCreateView.as_view(), name='admin_tag_preset_create'),
    path('tag-preset/<uuid:public_key>/delete/', views.AdminTagPresetDeleteView.as_view(), name='admin_tag_preset_delete'),
    path('template/<uuid:public_key>/toggle-visibility/', views.AdminTemplateToggleVisibilityView.as_view(), name='admin_template_toggle_visibility'),
    path('system-settings/', views.AdminSystemSettingsView.as_view(), name='admin_system_settings'),
]
