from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^search/google-custom-search/$', views.google_custom_search,
        name='google_custom_search'),
    url(r'^search/redirect-google-custom-search/$',
        views.redirect_google_custom_search,
        name='redirect_google_custom_search'),

    url(r'^search/topics/(?:t=(?P<topic>[a-zA-Z0-9][\w\ -]*))?$', views.topic_search,
        name='topic_search'),
    url(r'^search/all-topics/$', views.all_topics,
        name='all_topics'),
]
