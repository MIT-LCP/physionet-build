from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.console_home, name='console_home'),
    url(r'^storage-requests/$', views.storage_requests,
        name='storage_requests'),
]
