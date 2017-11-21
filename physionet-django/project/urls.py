from django.conf.urls import url
from django.urls import reverse_lazy

from .views import create_project


urlpatterns = [
    url(r'^create-project/$', create_project, name='create_project'),
]
