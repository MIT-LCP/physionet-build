from django.db import migrations
from django.contrib.contenttypes.models import ContentType
from project.models import SubmissionStatus


def migrate_archived_to_active(apps, schema_editor):
    """
    Copy all ArchivedProject data to the ActiveProject model.
    """
    AnonymousAccess = apps.get_model("project", "AnonymousAccess")
    ActiveProject = apps.get_model("project", "ActiveProject")
    ArchivedProject = apps.get_model("project", "ArchivedProject")
    Author = apps.get_model("project", "Author")
    CopyeditLog = apps.get_model("project", "CopyeditLog")
    EditLog = apps.get_model("project", "EditLog")
    Log = apps.get_model("project", "Log")
    Publication = apps.get_model("project", "Publication")
    Reference = apps.get_model("project", "Reference")
    Topic = apps.get_model("project", "Topic")
    UploadedDocument = apps.get_model("project", "UploadedDocument")

    # Get content types for both models
    archived_project_type = ContentType.objects.get_for_model(ArchivedProject)
    active_project_type = ContentType.objects.get_for_model(ActiveProject)

    for archived_project in ArchivedProject.objects.all():
        # Create a new ActiveProject instance
        active_project = ActiveProject(
            submission_status=SubmissionStatus.ARCHIVED.value,
        )
        for attr in [f.name for f in ArchivedProject._meta.fields]:
            if attr != 'id':
                setattr(active_project, attr, getattr(archived_project, attr))
        active_project.save()

        # Migrate references, authors, logs, etc from ArchivedProject to ActiveProject
        for model in [Reference,
                      Author,
                      Log,
                      AnonymousAccess,
                      Topic,
                      Publication,
                      UploadedDocument,
                      EditLog,
                      CopyeditLog]:
            items = model.objects.filter(
                content_type_id=archived_project_type.id, object_id=archived_project.id
            )
            for item in items:
                item.content_type_id = active_project_type.id
                item.object_id = active_project.id
                item.save()

        # Delete the archived project
        archived_project.delete()


def migrate_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0073_activeproject_archive_datetime"),
    ]

    operations = [
        migrations.RunPython(migrate_archived_to_active, migrate_backward),
    ]
