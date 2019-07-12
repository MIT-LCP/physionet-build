from django.urls import path

from . import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<year>/', views.news_year, name='news_year'),
    path('news/post/<news_id>', views.news_by_id, name='news_by_id'),
    path('feed.xml', views.news_rss, name='news_rss'),
]
