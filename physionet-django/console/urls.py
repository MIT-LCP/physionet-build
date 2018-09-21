from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^active-submissions/$', views.active_submissions, name='active_submissions'),
    url(r'^editing-submissions/$', views.editing_submissions, name='editing_submissions'),
    url(r'^edit-submission/(?P<submission_id>\d+)/$', views.edit_submission,
        name='edit_submission'),
    url(r'^project-list/$', views.project_list, name='project_list'),
    url(r'^storage-requests/$', views.storage_requests,
        name='storage_requests'),
    url(r'^user-list/$', views.user_list, name='user_list'),

]
