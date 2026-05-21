from django.urls import path, include
import oauth2_provider.views as oauth2_views
from django.conf import settings
from oauth2_provider.views import JwksInfoView
from oauth2_provider.views import UserInfoView as OIDCUserInfoView
from oauth.views import hello, UserInfoView, PhysioNetDiscoveryView

# OAuth2 provider endpoints. The OIDC userinfo and JWKS endpoints live here so
# DOT's discovery view (which does reverse("oauth2_provider:user-info") /
# reverse("oauth2_provider:jwks-info")) can resolve them inside the namespace.
oauth2_endpoint_views = [
    path("authorize/", oauth2_views.AuthorizationView.as_view(), name="authorize"),
    path("token/", oauth2_views.TokenView.as_view(), name="token"),
    path("revoke-token/", oauth2_views.RevokeTokenView.as_view(), name="revoke-token"),
    path("jwks/", JwksInfoView.as_view(), name="jwks-info"),
    path("oidc/userinfo", OIDCUserInfoView.as_view(), name="user-info"),
]

if settings.DEBUG:
    # OAuth2 Application Management endpoints
    oauth2_endpoint_views += [
        path("applications/", oauth2_views.ApplicationList.as_view(), name="list"),
        path(
            "applications/<pk>/",
            oauth2_views.ApplicationDetail.as_view(),
            name="detail",
        ),
        path(
            "applications/<pk>/delete/",
            oauth2_views.ApplicationDelete.as_view(),
            name="delete",
        ),
        path(
            "applications/<pk>/update/",
            oauth2_views.ApplicationUpdate.as_view(),
            name="update",
        ),
        path(
            "applications/register/",
            oauth2_views.ApplicationRegistration.as_view(),
            name="register",
        ),
    ]

    # OAuth2 Token Management endpoints
    oauth2_endpoint_views += [
        path(
            "authorized-tokens/",
            oauth2_views.AuthorizedTokensListView.as_view(),
            name="authorized-token-list",
        ),
        path(
            "authorized-tokens/<pk>/delete/",
            oauth2_views.AuthorizedTokenDeleteView.as_view(),
            name="authorized-token-delete",
        ),
    ]

urlpatterns = [
    # OAuth 2 endpoints:
    path(
        "",
        include(
            (oauth2_endpoint_views, "oauth2_provider"), namespace="oauth2_provider"
        ),
    ),
    path("hello", hello.as_view(), name="hello"),
    # Both slash forms route to the legacy view; OIDC userinfo lives under
    # oidc/ to avoid silently rejecting legacy tokens sent to /oauth/userinfo/.
    path("userinfo", UserInfoView.as_view(), name="userinfo"),
    path("userinfo/", UserInfoView.as_view()),
    path(".well-known/openid-configuration", PhysioNetDiscoveryView.as_view(), name="oidc-connect-discovery-info"),
]
