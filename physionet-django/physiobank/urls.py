from django.conf.urls import url
from . import views

urlpatterns = [
    # Physiobank home page
    url(r'^$', views.home),
    # Database index page
    url(r'^database/$', views.database_index),
    # Individual database page
    url(r'^database/(?P<dbslug>[\w-]+)/$', views.database),
    
    url(r'^database/(?P<dbslug>[\w-]+)/(?P<sublink>.*)$', views.database),
]