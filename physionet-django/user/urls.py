from django.conf.urls import url
from django.contrib.auth import views as auth_views
from django.urls import reverse

from . import views
from .forms import LoginForm, ResetForm, SetResetPasswordForm


urlpatterns = [
    url(r'^login/$', auth_views.LoginView.as_view(
        template_name='user/login.html',
        authentication_form=LoginForm,
        redirect_authenticated_user=True), name='login'),
    
    url(r'^logout/$', auth_views.LogoutView.as_view(), name='logout'),
    
    url(r'^register/$', views.register, name='register'),
    url(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.activate_user, name='activate_user'),
    
    # Individual home page/dashboard
    url(r'^home/$', views.user_home, name='user_home'),

    # Request password reset
    url(r'^resetpassword/$', auth_views.PasswordResetView.as_view(
        form_class=ResetForm, template_name='user/reset_password_request.html',
        #success_url=reverse('reset_password_sent')), name='reset_password_request'),
        success_url='/resetpassword/sent/',
        email_template_name='user/reset_password_email.html'),
        name='reset_password_request'),

    # Page shown after reset email has been sent
    url(r'^resetpassword/sent/$', auth_views.PasswordResetDoneView.as_view(
        template_name='user/reset_password_sent.html'),
        name='reset_password_sent'),

    # Prompt user to enter new password and carry out password reset (if url is valid)
    url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.PasswordResetConfirmView.as_view(
        form_class=SetResetPasswordForm,
        template_name='user/reset_password_confirm.html'),
        name='password_reset_confirm'),

    # Password reset successfully carried out
    url(r'^reset/done/$',
        auth_views.PasswordResetCompleteView.as_view(
        template_name='user/reset_password_done.html'),
        name='reset_password_done'),

    # Settings
    url(r'^settings/$', views.user_settings, name='user_settings'),
    url(r'^settings/profile/$', views.edit_profile, name='edit_profile'),
    url(r'^settings/password/$', views.edit_password, name='edit_password'),
    url(r'^settings/emails/$', views.edit_emails, name='edit_emails'),
    
    # Public user profile
    url(r'^users/(?P<email>[\w\-\.]+@[\w\-\.]+)/$', views.public_profile,
        name='public_profile'),
]

