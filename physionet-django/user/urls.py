from django.urls import path, re_path

from user import views


urlpatterns = [
    path('login/', views.login, name='login'),

    path('logout/', views.logout, name='logout'),

    path('register/', views.register, name='register'),
    re_path('^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.activate_user, name='activate_user'),

    # Request password reset
    path('reset-password/', views.reset_password_request,
         name='reset_password_request'),
    # Page shown after reset email has been sent
    path('reset-password/sent/', views.reset_password_sent,
         name='reset_password_sent'),
    # Prompt user to enter new password and carry out password reset (if url is valid)
    re_path('^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
            views.reset_password_confirm, name='reset_password_confirm'),
    # Password reset successfully carried out
    path('reset/complete/', views.reset_password_complete,
         name='reset_password_complete'),

    # Settings
    path('settings/', views.user_settings, name='user_settings'),
    path('settings/profile/', views.edit_profile, name='edit_profile'),
    path('settings/password/', views.edit_password, name='edit_password'),
    path('settings/password/changed/', views.edit_password_complete, name='edit_password_complete'),
    path('settings/emails/', views.edit_emails, name='edit_emails'),
    path('settings/username/', views.edit_username, name='edit_username'),
    path('settings/cloud/', views.edit_cloud, name='edit_cloud'),
    path('settings/orcid/', views.edit_orcid, name='edit_orcid'),
    path('authorcid/', views.auth_orcid, name='auth_orcid'),
    path('settings/credentialing/', views.edit_credentialing, name='edit_credentialing'),
    path('settings/credentialing/applications/',
        views.user_credential_applications, name='user_credential_applications'),
    path('settings/credentialing/applications/<user>/',
        views.user_credential_applications, name='user_credential_applications'),
    path('settings/agreements/', views.view_agreements, name='edit_agreements'),
    path('settings/agreements/<id>/',
        views.view_signed_agreement, name='view_signed_agreement'),

    # Current tokens are 20 characters long and consist of 0-9A-Za-z
    # Obsolete tokens are 34 characters long and also include a hyphen
    re_path('^verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[-0-9A-Za-z]{1,34})/$',
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
    path('credential-applications/<application_slug>/training-report/view/',
        views.training_report_view, name='training_report_view'),
]
