from django.db import migrations
import uuid


def backfill_uuids(apps, schema_editor):
    PublishedProject = apps.get_model('project', 'PublishedProject')
    for project in PublishedProject.objects.filter(public_project_uuid__isnull=True):
        project.public_project_uuid = uuid.uuid4()
        project.save(update_fields=['public_project_uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0090_publishedproject_public_project_uuid'),
    ]

    operations = [
        migrations.RunPython(backfill_uuids, migrations.RunPython.noop),
    ]
