from django.urls import path
from training import views


urlpatterns = [
    path('xyz/', views.view_training, name='trainings'),
    path('training/', views.create_op_training, name='create_training'),
    path('training/<int:training_id>/', views.create_op_training, name='create_training'),
    path('settings/platform-training/<int:training_id>/', views.take_training, name='platform_training'),
    path('settings/platform-training/', views.take_training, name='start_training')
]
