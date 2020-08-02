from django.urls import path, include
from waveforms.dash_apps.finished_apps import waveform_vis

from waveforms import views

urlpatterns = [
    path('django_plotly_dash/', include('django_plotly_dash.urls')),
    path('<project_slug>/<version>/', views.waveform_published_home, name='waveform_published_home'),
]
