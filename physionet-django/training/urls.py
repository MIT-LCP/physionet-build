from django.urls import path
from training import views


urlpatterns = [
    path('training/', views.on_platform_training, name='op_training'),
]
