from django.urls import path, re_path
from sso import views

urlpatterns = [
    path('sso/login/', views.sso_login, name='sso_login'),
    path('sso/register/', views.sso_register, name='sso_register'),
    re_path(
        '^sso/activate/(?P<uidb64>[0-9A-Za-z_-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/$',
        views.sso_activate_user,
        name='sso_activate_user',
    ),
]
