from django.db import migrations

from oauth.clients import create_python_client


def create_client(apps, schema_editor):
    create_python_client(apps.get_model("oauth2_provider", "Application"))


class Migration(migrations.Migration):
    """Register the PhysioNet Python package as a device flow client."""

    dependencies = [
        ("oauth2_provider", "0022_refreshtoken_token_family_index"),
    ]

    operations = [
        migrations.RunPython(create_client, migrations.RunPython.noop),
    ]
