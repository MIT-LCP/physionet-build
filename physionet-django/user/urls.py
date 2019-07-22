from django.contrib.auth import views as auth_views
from django.urls import path, re_path, reverse_lazy

from . import views
from .forms import LoginForm


urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        template_name='user/login.html',
        authentication_form=LoginForm,
        redirect_authenticated_user=True), name='login'),

    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('register/', views.register, name='register'),
    re_path('^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.activate_user, name='activate_user'),

    # Request password reset
    path('reset-password/', auth_views.PasswordResetView.as_view(
        template_name='user/reset_password_request.html',
        success_url=reverse_lazy('reset_password_sent'),
        email_template_name='user/email/reset_password_email.html'),
        name='reset_password_request'),
    # Page shown after reset email has been sent
    path('reset-password/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='user/reset_password_sent.html'),
        name='reset_password_sent'),
    # Prompt user to enter new password and carry out password reset (if url is valid)
    re_path('^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.PasswordResetConfirmView.as_view(
        template_name='user/reset_password_confirm.html',
        success_url=reverse_lazy('reset_password_complete')),
        name='reset_password_confirm'),
    # Password reset successfully carried out
    path('reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
        template_name='user/reset_password_complete.html'),
        name='reset_password_complete'),

    # Settings
    path('settings/', views.user_settings, name='user_settings'),
    path('settings/profile/', views.edit_profile, name='edit_profile'),
    path('settings/password/', auth_views.PasswordChangeView.as_view(
        success_url = reverse_lazy('edit_password_complete'),
        template_name='user/edit_password.html',
        ),
        name='edit_password'),
    path('settings/password/changed/', views.edit_password_complete, name='edit_password_complete'),
    path('settings/emails/', views.edit_emails, name='edit_emails'),
    path('settings/username/', views.edit_username, name='edit_username'),
    path('settings/cloud/', views.edit_cloud, name='edit_cloud'),
    path('settings/credentialing/', views.edit_credentialing, name='edit_credentialing'),
    path('settings/credentialing/applications/',
        views.user_credential_applications, name='user_credential_applications'),
    re_path('^verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.verify_email, name='verify_email'),

    # Public user profile
    path('users/<username>/', views.public_profile,
        name='public_profile'),
    path('users/<username>/profile-photo/', views.profile_photo,
        name='profile_photo'),

    path('credential-application/', views.credential_application,
        name='credential_application'),
    path('credential-reference/<application_slug>/',
        views.credential_reference, name='credential_reference'),
    path('credential-applications/<application_slug>/training-report/',
        views.training_report, name='training_report'),
]

