from django.urls import path

from entitlements.views import AccessibleProjectsView, EntitlementCheckView


urlpatterns = [
    path(
        'v1/entitlements/check/',
        EntitlementCheckView.as_view(),
        name='entitlement_check',
    ),
    path(
        'v1/entitlements/accessible-projects/',
        AccessibleProjectsView.as_view(),
        name='entitlement_accessible_projects',
    ),
]
