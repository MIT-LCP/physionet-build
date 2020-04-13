from django.db import migrations, models


def migrate_forward(apps, schema_editor):
    # Assume each published project's incremental size equals the
    # (positive) difference between its total size and the previous
    # version's total size.  (This may not be accurate, but gives
    # existing projects the benefit of the doubt.)

    PublishedProject = apps.get_model('project', 'PublishedProject')
    CoreProject = apps.get_model('project', 'CoreProject')
    for core in CoreProject.objects.all():
        previous_size = 0
        for pub in core.publishedprojects.order_by('publish_datetime').all():
            delta_size = pub.main_storage_size - previous_size
            if delta_size < 0:
                delta_size = 0
            pub.incremental_storage_size = delta_size
            previous_size = pub.main_storage_size
            pub.save(update_fields=['incremental_storage_size'])


def migrate_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0041_auto_20200317_0834'),
    ]

    operations = [
        migrations.AddField(
            model_name='publishedproject',
            name='incremental_storage_size',
            field=models.BigIntegerField(default=0, null=True),
        ),
        migrations.RunPython(migrate_forward, reverse_code=migrate_reverse),
    ]
