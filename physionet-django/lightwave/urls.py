from django.urls import path

from lightwave import views

urlpatterns = [
    path('<project_slug>/<project_version>', views.lightwave_home, name='lightwave_home'),
    path('server', views.lightwave_server, name='lightwave_server'),

    path('projects/<project_slug>/', views.lightwave_project_home,
         name='lightwave_project_home'),
    path('projects/<project_slug>/server', views.lightwave_project_server,
         name='lightwave_project_server'),
]
