from django.conf.urls import url
from . import views

urlpatterns = [
    # Physionetworkshome page
    url(r'^$', views.home, name='home'),

    # Create new project
    url(r'^create/$', views.create_project, name='create'),

]
