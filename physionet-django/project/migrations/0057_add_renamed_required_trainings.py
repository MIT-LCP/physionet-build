from itertools import chain

from django.db import migrations, models

from project.modelcomponents.access import AccessPolicy


def migrate_forward(apps, schema_editor):
    ActiveProject = apps.get_model('project', 'ActiveProject')
    ArchivedProject = apps.get_model('project', 'ArchivedProject')
    PublishedProject = apps.get_model('project', 'PublishedProject')

    filter = models.Q(access_policy__gte=AccessPolicy.CREDENTIALED)
    for project in chain(
        ActiveProject.objects.filter(filter),
        ArchivedProject.objects.filter(filter),
        PublishedProject.objects.filter(filter)
    ):
        project.required_trainings.set(project.required_training.all())


def migrate_backward(apps, schema_editor):
    ActiveProject = apps.get_model('project', 'ActiveProject')
    ArchivedProject = apps.get_model('project', 'ArchivedProject')
    PublishedProject = apps.get_model('project', 'PublishedProject')

    filter = models.Q(access_policy__gte=AccessPolicy.CREDENTIALED)
    for project in chain(
        ActiveProject.objects.filter(filter),
        ArchivedProject.objects.filter(filter),
        PublishedProject.objects.filter(filter)
    ):
        project.required_training.set(project.required_trainings.all())


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0056_dataaccessrequest_duration'),
    ]

    operations = [
        migrations.AddField(
            model_name='activeproject',
            name='required_trainings',
            field=models.ManyToManyField(related_name='activeproject_temp', to='user.TrainingType'),
        ),
        migrations.AddField(
            model_name='archivedproject',
            name='required_trainings',
            field=models.ManyToManyField(related_name='archivedproject_temp', to='user.TrainingType'),
        ),
        migrations.AddField(
            model_name='publishedproject',
            name='required_trainings',
            field=models.ManyToManyField(related_name='publishedproject_temp', to='user.TrainingType'),
        ),
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
