from django.db import migrations, models

from user.trainingreport import (find_training_report_url,
                                 TrainingCertificateError)


def migrate_forward(apps, schema_editor):
    # For each existing application, check if the uploaded file
    # contains a valid training report URL.  If the uploaded file
    # can't be read, it is ignored.
    CredentialApplication = apps.get_model('user', 'CredentialApplication')
    for appl in CredentialApplication.objects.all():
        try:
            if appl.training_completion_report:
                with open(appl.training_completion_report.path, 'rb') as f:
                    report_url = find_training_report_url(f)
                if report_url:
                    appl.training_completion_report_url = report_url
                    appl.save(update_fields=['training_completion_report_url'])
        except (OSError, TrainingCertificateError):
            pass


def migrate_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    # This data migration could take a long time so must not run in a
    # transaction.
    atomic = False

    dependencies = [
        ('user', '0029_credentialapplication_url'),
    ]

    operations = [
        migrations.RunPython(migrate_forward, reverse_code=migrate_reverse),
    ]
