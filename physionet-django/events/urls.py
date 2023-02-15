from django.urls import path

from events import views


urlpatterns = [
    path('', views.event_home, name='event_home'),
    path('<slug:event_slug>/', views.event_detail, name='event_detail'),
    path('<slug:event_slug>/edit_event/', views.update_event, name='update_event'),
    path('<slug:event_slug>/details/', views.get_event_details, name='get_event_details'),
    path('<slug:event_slug>/participant/<int:participant_id>/toggle_cohost_status', views.toggle_cohost_status,
         name='toggle_cohost_status'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {'event_slug': 'iLII4L9jSDFh', }
