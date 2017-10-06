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

    url(r'^users/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', views.user_home, name='user_home'), 
    url(r'^home/$', views.dashboard, name='home'),
    url(r'^login/$', views.login, name='login'),
    url(r'^logout/$', views.logout, name='logout'),
    url(r'^reset/$', views.reset, name='reset'),
    url(r'^profile/edit$', views.edit, name='index'),
]

# # Private dasboard
# /dashboard/
# # public page to the world
# /users/felipe.torres.cs@gmail.com
# # page to edit the user
# /profile


# /users/felipe.torres.cs@gmail.com
# /users/felipe.torres.cs@gmail.com/settings or profile
# /users/felipe.torres.cs@gmail.com/home
