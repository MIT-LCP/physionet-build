from django.urls import path

from . import views

urlpatterns = [
    path('', views.lightwave_home, name='lightwave_home'),
    path('server', views.lightwave_server, name='lightwave_server'),
    path('js/<path:file_name>', views.lightwave_js, name='lightwave_js'),
    path('css/<path:file_name>', views.lightwave_css, name='lightwave_css'),
    path('doc/<path:file_name>', views.lightwave_doc, name='lightwave_doc'),

    path('projects/<project_slug>/', views.lightwave_project_home,
         name='lightwave_project_home'),
    path('projects/<project_slug>/server', views.lightwave_project_server,
         name='lightwave_project_server'),
    path('projects/<project_slug>/js/<path:file_name>',
         views.lightwave_js, name='lightwave_project_js'),
    path('projects/<project_slug>/css/<path:file_name>',
         views.lightwave_css, name='lightwave_project_css'),
    path('projects/<project_slug>/doc/<path:file_name>',
         views.lightwave_doc, name='lightwave_project_doc'),
]
