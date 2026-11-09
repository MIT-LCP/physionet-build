"""
Remove the OAuth access tokens that the token settings page created
before personal access tokens replaced them.

Those tokens were issued through the application named by
OAUTH_CLIENT_APP_NAME, which existed only for that page. They were stored
in plain text and are no longer listed on the page, so users could not
see or revoke them.
"""

from django.conf import settings
from django.db import migrations


def remove_settings_page_tokens(apps, schema_editor):
    app_name = getattr(settings, "OAUTH_CLIENT_APP_NAME", "")
    if not app_name:
        return
    AccessToken = apps.get_model("oauth2_provider", "AccessToken")
    AccessToken.objects.filter(application__name=app_name).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0077_personalaccesstoken"),
        ("oauth2_provider", "0006_alter_application_client_secret"),
    ]

    operations = [
        migrations.RunPython(remove_settings_page_tokens, migrations.RunPython.noop),
    ]
