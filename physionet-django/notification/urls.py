from django.urls import path

from notification import views


urlpatterns = [
    path('news/', views.news, name='news'),
    path('news/<int:year>/', views.news_year, name='news_year'),
    path('news/post/<news_slug>/', views.news_by_slug, name='news_by_slug'),
    path('feed.xml', views.news_rss, name='news_rss'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('notifications/unread-count/', views.unread_count, name='unread_count'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'year': '2018',
    'news_id': '1',
    'news_slug': 'cloud-migration',
}

TEST_CASES = {
    'notification_list': {
        '_user_': 'george',
    },
    'mark_notification_read': {
        '_user_': 'george',
        'notification_id': '1',
        '_skip_': True,
    },
    'mark_all_read': {
        '_user_': 'george',
        '_skip_': True,
    },
    'unread_count': {
        '_user_': 'george',
    },
}
