from django.urls import path
from training import views


urlpatterns = [
    path('training/', views.on_platform_training, name='op_training'),
    path('settings/platform-training/<int:training_id>/', views.take_training, name='platform_training'),
    path('settings/platform-training/<int:training_id>/module/<int:module_id>/', views.take_module_training,
         name='platform_training_module'),
    path('settings/platform-training/update-module-progress/', views.update_module_progress,
         name='update_module_progress'),
    path('settings/platform-training/', views.take_training, name='start_training')
]
