from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0006_add_organizer_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='challengeconfiguration',
            name='evaluation_script_path',
        ),
        migrations.RemoveField(
            model_name='challengeconfiguration',
            name='validation_data_path',
        ),
        migrations.RemoveField(
            model_name='challengeconfiguration',
            name='test_data_path',
        ),
        migrations.AddField(
            model_name='challengeconfiguration',
            name='validation_data_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS URI for the private validation data.',
            ),
        ),
        migrations.AddField(
            model_name='challengeconfiguration',
            name='test_data_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS URI for the private final test data.',
            ),
        ),
        migrations.AddField(
            model_name='challengeconfiguration',
            name='evaluation_script_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS URI for the evaluation/scoring script.',
            ),
        ),
    ]
