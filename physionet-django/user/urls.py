from django.urls import path, re_path
from user import views
from django.conf import settings


login_view = views.sso_login if settings.ENABLE_SSO else views.login


urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", views.logout, name="logout"),
    # Settings
    path("settings/", views.user_settings, name="user_settings"),
    path("settings/profile/", views.edit_profile, name="edit_profile"),
    path("settings/emails/", views.edit_emails, name="edit_emails"),
    path("settings/username/", views.edit_username, name="edit_username"),
    path("settings/cloud/", views.edit_cloud, name="edit_cloud"),
    path("settings/orcid/", views.edit_orcid, name="edit_orcid"),
    path("authorcid/", views.auth_orcid, name="auth_orcid"),
    path(
        "settings/credentialing/", views.edit_credentialing, name="edit_credentialing"
    ),
    path(
        "settings/credentialing/applications/",
        views.user_credential_applications,
        name="user_credential_applications",
    ),
    path(
        "settings/certification/", views.edit_certification, name="edit_certification"
    ),
    path("settings/training/", views.edit_training, name="edit_training"),
    path(
        "settings/training/<int:training_id>/",
        views.edit_training_detail,
        name="edit_training_detail",
    ),
    path("settings/agreements/", views.view_agreements, name="edit_agreements"),
    path(
        "settings/agreements/<int:dua_signature_id>/",
        views.view_signed_agreement,
        name="view_signed_agreement",
    ),
    # Current tokens are 20 characters long and consist of 0-9A-Za-z
    # Obsolete tokens are 34 characters long and also include a hyphen
    re_path(
        r"^verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[-0-9A-Za-z]{1,34})/$",
        views.verify_email,
        name="verify_email",
    ),
    # Public user profile
    path("users/<username>/", views.public_profile, name="public_profile"),
    path("users/<username>/profile-photo/", views.profile_photo, name="profile_photo"),
    path(
        "credential-application/",
        views.credential_application,
        name="credential_application",
    ),
    # TODO: remove this after 30 days of commit merge, we want let the old links that was sent to the referees work
    path(
        "credential-reference/<application_slug>/",
        views.credential_reference,
        name="credential_reference",
    ),
    path(
        "credential-reference/<application_slug>/<verification_token>/",
        views.credential_reference_verification,
        name="credential_reference_verification",
    ),
    path(
        "trainings/<int:training_id>/report/",
        views.training_report,
        name="training_report",
    ),
]

if not settings.ENABLE_SSO:
    urlpatterns.extend(
        [
            path("register/", views.register, name="register"),
            path("settings/password/", views.edit_password, name="edit_password"),
            path(
                "settings/password/changed/",
                views.edit_password_complete,
                name="edit_password_complete",
            ),
            re_path(
                r"^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/$",
                views.activate_user,
                name="activate_user",
            ),
            # Request password reset
            path(
                "reset-password/",
                views.reset_password_request,
                name="reset_password_request",
            ),
            # Page shown after reset email has been sent
            path(
                "reset-password/sent/",
                views.reset_password_sent,
                name="reset_password_sent",
            ),
            # Prompt user to enter new password and carry out password reset (if url is valid)
            re_path(
                r"^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/$",
                views.reset_password_confirm,
                name="reset_password_confirm",
            ),
            # Password reset successfully carried out
            path(
                "reset/complete/",
                views.reset_password_complete,
                name="reset_password_complete",
            ),
        ]
    )

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    "_user_": "aewj",
    "training_id": 106,
    "dua_signature_id": 1,
    "application_slug": "Osm0FMaavviixpsL26v2",
    "verification_token": "rJ2i7vlzh6AgZ1Wwtcz8zCoI5BqxH0kU",
    "username": "rgmark",
}
TEST_CASES = {
    "verify_email": {
        "uidb64": "MjEx",
        "token": "oax3ZcG47GYUhAobbJyp",
    },
    # Testing activate_user and reset_password_confirm requires a
    # dynamically-generated token.  Skip these URLs for now.
    "activate_user": {"uidb64": "x", "token": "x", "_skip_": True},
    "reset_password_confirm": {"uidb64": "x", "token": "x", "_skip_": True},
    # Testing auth_orcid requires a mock oauth server.  Skip this URL.
    "auth_orcid": {"_skip_": True},
}
