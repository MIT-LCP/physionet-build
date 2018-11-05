from django.conf.urls import url
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from . import views
from .forms import LoginForm


urlpatterns = [
    url(r'^login/$', auth_views.LoginView.as_view(
        template_name='user/login.html',
        authentication_form=LoginForm,
        redirect_authenticated_user=True), name='login'),

    url(r'^logout/$', auth_views.LogoutView.as_view(), name='logout'),

    url(r'^register/$', views.register, name='register'),
    url(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.activate_user, name='activate_user'),

    # Request password reset
    url(r'^reset-password/$', auth_views.PasswordResetView.as_view(
        template_name='user/reset_password_request.html',
        success_url=reverse_lazy('reset_password_sent'),
        email_template_name='user/email/reset_password_email.html'),
        name='reset_password_request'),
    # Page shown after reset email has been sent
    url(r'^reset-password/sent/$', auth_views.PasswordResetDoneView.as_view(
        template_name='user/reset_password_sent.html'),
        name='reset_password_sent'),
    # Prompt user to enter new password and carry out password reset (if url is valid)
    url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.PasswordResetConfirmView.as_view(
        template_name='user/reset_password_confirm.html',
        success_url=reverse_lazy('reset_password_complete')),
        name='reset_password_confirm'),
    # Password reset successfully carried out
    url(r'^reset/complete/$',
        auth_views.PasswordResetCompleteView.as_view(
        template_name='user/reset_password_complete.html'),
        name='reset_password_complete'),

    # Settings
    url(r'^settings/$', views.user_settings, name='user_settings'),
    url(r'^settings/profile/$', views.edit_profile, name='edit_profile'),
    url(r'^settings/password/$', auth_views.PasswordChangeView.as_view(
        success_url = reverse_lazy('edit_password_complete'),
        template_name='user/edit_password.html',
        ),
        name='edit_password'),
    url(r'^settings/password/changed/$', views.edit_password_complete, name='edit_password_complete'),
    url(r'^settings/emails/$', views.edit_emails, name='edit_emails'),
    url(r'^settings/username/$', views.edit_username, name='edit_username'),
    url(r'^settings/credentialing/$', views.edit_credentialing, name='edit_credentialing'),
    url(r'^verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.verify_email, name='verify_email'),

    # Individual home page/dashboard
    url(r'^home/$', views.user_home, name='user_home'),

    # Public user profile
    url(r'^users/(?P<username>[\w\-\.]+)/$', views.public_profile,
        name='public_profile'),
    url(r'^users/(?P<username>[\w\-\.]+)/profile-photo/$', views.profile_photo,
        name='profile_photo'),

    url(r'^credential-application/$', views.credential_application,
        name='credential_application'),
]

