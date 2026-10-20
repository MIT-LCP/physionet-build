from django.urls import path

from challenge import views

urlpatterns = [
    path('', views.challenge_list, name='challenge_list'),
    path('<slug:challenge_slug>/',
         views.challenge_detail, name='challenge_detail'),
    path('<slug:challenge_slug>/rules/',
         views.challenge_rules, name='challenge_rules'),
    path('<slug:challenge_slug>/leaderboard/',
         views.challenge_leaderboard, name='challenge_leaderboard'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'challenge_slug': 'demo-ecg-challenge',
}
