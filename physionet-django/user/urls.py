from django.conf.urls import url
from django.contrib.auth.views import LoginView, LogoutView

from . import views
from .forms import LoginForm


urlpatterns = [
    url(r'^login/$', LoginView.as_view(
        template_name='user/login.html',
        authentication_form=LoginForm,
        redirect_authenticated_user=True), name='login'),
    url(r'^logout/$', LogoutView.as_view(), name='logout'),
    url(r'^register/$', views.register, name='register'),
    
    url(r'^resetpassword/$', views.reset_password, name='reset_password'),
    
    url(r'^home/$', views.user_home, name='user_home'),
    url(r'^settings/profile/$', views.edit_profile, name='edit_profile'),

    url(r'^users/(?P<email>[\w\-\.]+@[\w\-\.]+)/$', views.public_profile,
        name='public_profile'),
]
