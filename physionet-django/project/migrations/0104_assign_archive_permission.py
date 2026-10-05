from django.db import migrations


def assign_archive_permission(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

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

    group, _ = Group.objects.get_or_create(name="Managing Editor")
    group.permissions.add(permission)


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0103_alter_activeproject_options")
    ]

    operations = [
        migrations.RunPython(assign_archive_permission, migrations.RunPython.noop),
    ]
    