from django.conf.urls import url
# from django.contrib import admin
# from django.contrib.auth import views as auth_views
# from django.contrib.auth.views import LoginView
# from django.conf import settings
# from django.conf.urls.static import static

# from django.views.generic.base import TemplateView
from . import views
# from . import forms
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', views.user_home, name='user_home'), 
    url(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/edit/$', views.edit, name='edit'),
    url(r'^reset_password/[0-9a-z-]+/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', views.reset_password, name='reset_password'),
    url(r'^reset/$', views.reset, name='reset'),

]
