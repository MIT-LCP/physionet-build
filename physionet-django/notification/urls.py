from django.urls import path

from notification import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<int:year>/', views.news_year, name='news_year'),
    path('news/post/<news_slug>', views.news_by_slug, name='news_by_slug'),
    path('feed.xml', views.news_rss, name='news_rss'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'year': '2018',
    'news_id': '1',
    'news_slug': 'cloud-migration',
}
