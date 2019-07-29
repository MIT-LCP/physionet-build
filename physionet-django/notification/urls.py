from django.urls import path

from . import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<int:year>/', views.news_year, name='news_year'),
    path('feed.xml', views.news_rss, name='news_rss'),
]
