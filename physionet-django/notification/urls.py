from django.urls import path

from notification import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<int:year>/', views.news_year, name='news_year'),
    path('news/post/<int:news_id>', views.news_by_id, name='news_by_id'),
    path('feed.xml', views.news_rss, name='news_rss'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'year': '2018',
    'news_id': '1',
}
