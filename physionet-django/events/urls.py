from django.urls import path

from events import views


urlpatterns = [
    path('', views.event_home, name='event_home'),
    path('create/', views.create_event, name='create_event'),
    path('<slug:event_slug>/', views.event_detail, name='event_detail'),
    path('<slug:event_slug>/edit_event/', views.update_event, name='update_event'),
    path('<slug:event_slug>/details/', views.get_event_details, name='get_event_details'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'event_slug': 'iLII4L9jSDFh',
    'participant_id': 1,
    '_user_': 'rgmark',
}
