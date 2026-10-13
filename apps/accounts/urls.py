from django.urls import path

from apps.accounts import views

urlpatterns = [
    path('', views.LoginView.as_view(), name='login'),
    path('', views.LoginView.as_view(), name='account_login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('password/forgot/', views.ForgotPasswordView.as_view(), name='forgot_password'),
    path('password/set/<uuid:public_key>/<token>/', views.SetPasswordView.as_view(), name='set_password'),
    path('password/change/', views.ChangePasswordView.as_view(), name='change_password'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/activity/', views.ProfileActivityFeedView.as_view(), name='profile_activity_feed'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
]
