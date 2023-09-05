import os

from django.db import models
from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def migrate_forward(apps, schema_editor):
    CredentialReview = apps.get_model('user', 'CredentialReview')

    CredentialReview.objects.filter(status__gte=30).update(status=models.F('status') - 10)


def migrate_backward(apps, schema_editor):
    CredentialApplication = apps.get_model('user', 'CredentialApplication')
    CredentialReview = apps.get_model('user', 'CredentialReview')
    Training = apps.get_model('user', 'Training')

    CredentialReview.objects.filter(status__gte=20).update(status=models.F('status') + 10)

    for training in Training.objects.select_related('user').all():
        credential_application = CredentialApplication.objects.filter(slug=training.slug).first()
        if credential_application is None:
            continue

        report_url = None if not training.completion_report_url else training.completion_report_url

        credential_application.training_completion_report = training.completion_report.name
        credential_application.training_completion_report_url = report_url
        credential_application.training_completion_date = training.application_datetime
        credential_application.training_course_name = training.training_type.name
        credential_application.save()


class Migration(migrations.Migration):
    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('user', '0035_training_1'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credentialreview',
            name='status',
            field=models.PositiveSmallIntegerField(
                choices=[
                    ('', '-----------'),
                    (0, 'Not in review'),
                    (10, 'Initial review'),
                    (20, 'ID check'),
                    (30, 'Reference'),
                    (40, 'Reference response'),
                    (50, 'Final review'),
                ],
                default=10,
            ),
        ),
        migrations.RunPython(migrate_forward, migrate_backward),
        migrations.RemoveField(
            model_name='credentialapplication',
            name='training_completion_date',
        ),
        migrations.RemoveField(
            model_name='credentialapplication',
            name='training_completion_report',
        ),
        migrations.RemoveField(
            model_name='credentialapplication',
            name='training_completion_report_url',
        ),
        migrations.RemoveField(
            model_name='credentialapplication',
            name='training_course_name',
        ),
        migrations.RemoveField(
            model_name='credentialreview',
            name='citi_report_attached',
        ),
        migrations.RemoveField(
            model_name='credentialreview',
            name='training_all_modules',
        ),
        migrations.RemoveField(
            model_name='credentialreview',
            name='training_current',
        ),
        migrations.RemoveField(
            model_name='credentialreview',
            name='training_name_match',
        ),
        migrations.RemoveField(
            model_name='credentialreview',
            name='training_privacy_complete',
        ),
    ]
