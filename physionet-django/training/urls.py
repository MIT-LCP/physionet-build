from django.urls import path
from training import views
from user.views import edit_training


urlpatterns = [
    path('settings/platform-training/<training_slug>/', views.take_training, name='platform_training'),
    path('settings/platform-training/<training_slug>/module/<int:module_order>-<int:order>/',
         views.current_module_block,
         name='current_module_block'),
]

# Parameters for testing URLs
TEST_DEFAULTS = {
    'training_slug': 'world-101-introduction-to-continents-and-countries',
    '_user_': 'tompollard',
}
TEST_CASES = {
    'platform_training': {
    },
    'current_module_block': {
        'module_order': 1,
        'order': 2
    },
}
