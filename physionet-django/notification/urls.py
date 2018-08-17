from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^news/$', views.news, name='news'),
    url(r'^news/(?P<year>\d+)/$', views.news_year, name='news_year'),
]
