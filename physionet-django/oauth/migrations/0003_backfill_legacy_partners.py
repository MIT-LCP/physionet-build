from django.conf import settings
from django.db import migrations


def backfill_legacy_partners(apps, schema_editor):
    """For every existing Application, create a 'Legacy: <client_id>' Partner."""
    Application = apps.get_model(settings.OAUTH2_PROVIDER_APPLICATION_MODEL)
    Partner = apps.get_model('oauth', 'Partner')
    for app in Application.objects.all():
        Partner.objects.get_or_create(
            application=app,
            defaults={
                'organization_name': f'Legacy: {app.client_id}',
                'allowed_scopes': [],
                'status': 'active',
                'created_by': None,
            },
        )


def remove_legacy_partners(apps, schema_editor):
    """Reverse: delete only legacy rows; keep admin-created Partners."""
    Partner = apps.get_model('oauth', 'Partner')
    Partner.objects.filter(organization_name__startswith='Legacy: ').delete()


class Migration(migrations.Migration):
    """Backfill Partner rows for Applications that predate this app.

    Marked as a "late" migration (MIGRATE_AFTER_INSTALL = True) so the
    upgrade flow applies the schema (0001_initial) ahead of the new
    server code but defers this data step until after the codebase is
    swapped. Without that deferral, the backfilled Partner rows are
    orphaned when the old codebase deletes an Application (Django
    handles cascade in Python and the old code can't see Partner).
    """

    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('oauth', '0002_partner_requires_pkce'),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_partners, remove_legacy_partners),
    ]
