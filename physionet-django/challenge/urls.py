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
    path('<slug:challenge_slug>/register/',
         views.challenge_register, name='challenge_register'),
    path('<slug:challenge_slug>/submit/',
         views.challenge_submit, name='challenge_submit'),
    path('<slug:challenge_slug>/submissions/',
         views.challenge_my_submissions, name='challenge_my_submissions'),
    path('<slug:challenge_slug>/submissions/<int:submission_id>/',
         views.challenge_submission_detail, name='challenge_submission_detail'),
    # Team
    path('<slug:challenge_slug>/team/',
         views.challenge_team, name='challenge_team'),
    path('<slug:challenge_slug>/team/create/',
         views.challenge_team_create, name='challenge_team_create'),
    path('<slug:challenge_slug>/team/invite/',
         views.challenge_team_invite, name='challenge_team_invite'),
    path('<slug:challenge_slug>/team/invitation/<int:invitation_id>/',
         views.challenge_team_invitation_respond,
         name='challenge_team_invitation_respond'),
    # Organizer management
    path('<slug:challenge_slug>/manage/',
         views.challenge_manage, name='challenge_manage'),
    path('<slug:challenge_slug>/manage/submissions/',
         views.challenge_manage_submissions,
         name='challenge_manage_submissions'),
]

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'challenge_slug': 'test-challenge',
    'submission_id': 1,
    'invitation_id': 1,
    '_user_': 'rgmark',
}
