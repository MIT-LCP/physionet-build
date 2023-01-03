from django.urls import path

from events import views


urlpatterns = [
    path('', views.event_home, name='event_home'),
    path('<slug:event_slug>/', views.event_add_participant, name='event_add_participant'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {'event_slug': 'iLII4L9jSDFh', }
