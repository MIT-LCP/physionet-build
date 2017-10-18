from django.conf.urls import url
from django.contrib.auth import views as auth_views

# import LoginView, LogoutView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView

from .views import register, user_home, activate_user
from .forms import LoginForm, ResetForm, SetResetPasswordForm


urlpatterns = [
    url(r'^login/$', auth_views.LoginView.as_view(
        template_name='user/login.html',
        authentication_form=LoginForm,
        redirect_authenticated_user=True), name='login'),
    url(r'^logout/$', auth_views.LogoutView.as_view(), name='logout'),
    url(r'^register/$', register, name='register'),
    # Individual home page/dashboard
    url(r'^home/$', user_home, name='userhome'),


    url(r'^password_reset/$', auth_views.PasswordResetView.as_view(
        form_class=ResetForm, template_name='user/reset.html'), 
        name='password_reset'),
    url(r'^password_reset/done/$', auth_views.PasswordResetDoneView.as_view(
        template_name='user/password_reset_done.html'), 
        name='password_reset_done'),


    url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.PasswordResetConfirmView.as_view(
        form_class=SetResetPasswordForm, 
        template_name='user/password_reset_confirm.html'),
        name='password_reset_confirm'),

    url(r'^reset/done/$',
        auth_views.PasswordResetCompleteView.as_view(
        template_name='user/password_reset_complete.html'),
        name='password_reset_complete'),

    url(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        activate_user, name='activate_user'),

]

