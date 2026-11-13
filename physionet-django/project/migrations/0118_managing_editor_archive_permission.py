from django.db import migrations


def grant_archive_permission(apps, schema_editor):
    """
    Grant can_archive_project to the managing editor group.

    Migration 0104 only looked for a group named "Managing Editor", and it
    skipped the grant if the permission already existed. Sites where the
    group has a different capitalisation (e.g. "managing editor") never got
    the permission, so managing editors could not archive projects or manage
    revision deadlines.
    """
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')

    groups = Group.objects.filter(name__iexact='managing editor')
    if not groups.exists():
        return

    # Permissions are normally created after migrations finish, so on a fresh
    # database they may not exist yet.
    content_type, _ = ContentType.objects.get_or_create(app_label='project', model='activeproject')
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename='can_archive_project',
        defaults={'name': 'Can archive ActiveProjects'},
    )
    for group in groups:
        group.permissions.add(permission)


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0117_revision_deadline'),
    ]

    operations = [
        migrations.RunPython(grant_archive_permission, migrations.RunPython.noop),
    ]
