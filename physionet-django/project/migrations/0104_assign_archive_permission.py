from django.db import migrations


def assign_archive_permission(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    # Only run if the permission doesn't already exist
    if Permission.objects.filter(codename="can_archive_project").exists():
        return

    # Permissions are normally created after migrations finish, so on a fresh
    # database they may not exist yet. Create them here if needed.
    content_type, _ = ContentType.objects.get_or_create(
        app_label="project", model="activeproject"
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="can_archive_project",
        defaults={"name": "Can archive ActiveProjects"},
    )

    try:
        group = Group.objects.get(name="Managing Editor")
        group.permissions.add(permission)
    except Group.DoesNotExist:
        # Group doesn't exist yet, skip
        # (It will be created by fixture if needed)
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0103_alter_activeproject_options")
    ]

    operations = [
        migrations.RunPython(assign_archive_permission, migrations.RunPython.noop),
    ]
