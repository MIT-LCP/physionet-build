from django.db import migrations, models


def migrate_forward(apps, schema_editor):
    PublishedProject = apps.get_model("project", "PublishedProject")
    ActiveProject = apps.get_model("project", "ActiveProject")
    ArchivedProject = apps.get_model("project", "ArchivedProject")

    for project in PublishedProject.objects.all():
        refs = project.references.all().order_by('id')
        for n, ref in enumerate(refs):
            ref.order = n + 1
            ref.save()

    for project in ActiveProject.objects.all():
        refs = project.references.all().order_by('id')
        for n, ref in enumerate(refs):
            ref.order = n + 1
            ref.save()

    for project in ArchivedProject.objects.all():
        refs = project.references.all().order_by('id')
        for n, ref in enumerate(refs):
            ref.order = n + 1
            ref.save()


def migrate_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('project', '0065_editor_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='publishedreference',
            name='order',
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.AddField(
            model_name='reference',
            name='order',
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.AlterUniqueTogether(
            name='publishedreference',
            unique_together={('description', 'project', 'order')},
        ),
        migrations.AlterUniqueTogether(
            name='reference',
            unique_together={('description', 'object_id', 'order')},
        ),
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
