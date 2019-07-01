from django.urls import path

from . import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<year>/', views.news_year, name='news_year'),
    path('news/<guid>', views.news_guid, name='news_guid'),
    path('feed.xml', views.news_rss, name='news_rss'),
]
