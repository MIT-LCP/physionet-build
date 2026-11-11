"""
OAuth applications that PhysioNet itself provides.

The PhysioNet Python package signs users in with the device flow
(RFC 8628): it shows a short code, and the user approves the sign-in in
a browser. It is a public client, so it has no secret, and its client ID
is fixed so that the package works with any PhysioNet site.
"""

PYTHON_CLIENT_ID = "physionet-python-client"
PYTHON_CLIENT_NAME = "PhysioNet Python package"

# Scopes that a device flow client may request, and the scopes it gets
# if it does not ask for any.
DEVICE_FLOW_SCOPES = {"data:download", "profile:read"}
DEVICE_FLOW_DEFAULT_SCOPES = ["data:download"]


def create_python_client(application_model):
    """
    Create the Python package's application if it does not exist.

    Takes the Application model as an argument so that migrations can
    pass their historical model.
    """
    application_model.objects.get_or_create(
        client_id=PYTHON_CLIENT_ID,
        defaults={
            "name": PYTHON_CLIENT_NAME,
            "client_type": "public",
            "authorization_grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_secret": "",
            "redirect_uris": "",
            "skip_authorization": False,
        },
    )


def is_device_client(application):
    """Return True if the application signs in with the device flow."""
    return (
        application is not None
        and application.authorization_grant_type == application.GRANT_DEVICE_CODE
    )
