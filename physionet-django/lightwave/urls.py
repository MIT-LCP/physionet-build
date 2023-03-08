from django.urls import path

from lightwave import views

urlpatterns = [
    path('', views.lightwave_home, name='lightwave_home'),
    path('server', views.lightwave_server, name='lightwave_server'),

    path('projects/<project_slug>/', views.lightwave_project_home,
         name='lightwave_project_home'),
    path('projects/<project_slug>/server', views.lightwave_project_server,
         name='lightwave_project_server'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'project_slug': 'SHuKI1APLrwWCqxSQnSk',
    '_user_': 'rgmark',
}
