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
    # Individual home page/dashboard
    url(r'^home/$', views.user_home, name='userhome'),

]
