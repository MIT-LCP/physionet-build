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
        # The old page could not issue tokens without this setting, so there
        # is normally nothing to remove. Say so, in case the setting was
        # removed after tokens were created.
        print(
            "\n  WARNING: OAUTH_CLIENT_APP_NAME is not set, so OAuth tokens created by the"
            "\n  token settings page (if any) were not removed."
        )
        return
    AccessToken = apps.get_model("oauth2_provider", "AccessToken")
    deleted, _ = AccessToken.objects.filter(application__name=app_name).delete()
    print(f"\n  Removed {deleted} OAuth token(s) issued by the token settings page ({app_name}).")


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0077_personalaccesstoken"),
        ("oauth2_provider", "0006_alter_application_client_secret"),
    ]

    operations = [
        migrations.RunPython(remove_settings_page_tokens, migrations.RunPython.noop),
    ]
