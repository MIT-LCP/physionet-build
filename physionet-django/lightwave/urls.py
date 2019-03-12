from django.urls import path

from . import views

urlpatterns = [
    path('', views.lightwave_home,
        name='lightwave_home'),
]
