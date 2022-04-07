from django.db import migrations, models


def migrate_forward(apps, schema_editor):
    CredentialReview = apps.get_model('user', 'CredentialReview')
    CredentialReview.objects.filter(status__gte=20).update(status=models.F('status') - 10)


def migrate_backward(apps, schema_editor):
    CredentialReview = apps.get_model('user', 'CredentialReview')
    CredentialReview.objects.filter(status__gte=20).update(status=models.F('status') + 10)


class Migration(migrations.Migration):
    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('user', '0042_permissions_2'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credentialreview',
            name='status',
            field=models.PositiveSmallIntegerField(
                choices=[(
                    '', '-----------'),
                    (0, 'Not in review'),
                    (10, 'ID check'),
                    (20, 'Reference'),
                    (30, 'Reference response'),
                    (40, 'Final review')
                ],
                default=10),
        ),
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
