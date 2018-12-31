from django.urls import path

from . import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<year>/', views.news_year, name='news_year'),
]
