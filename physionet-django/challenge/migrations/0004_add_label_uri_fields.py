from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0003_add_top_n_advancement_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='challengeconfiguration',
            name='validation_labels_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS URI for the validation ground-truth labels (kept separate from input data).',
            ),
        ),
        migrations.AddField(
            model_name='challengeconfiguration',
            name='test_labels_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS URI for the test ground-truth labels (kept separate from input data).',
            ),
        ),
        migrations.AddField(
            model_name='challenge',
            name='validation_labels_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS path for the validation ground-truth labels (kept separate from input data).',
            ),
        ),
        migrations.AddField(
            model_name='challenge',
            name='test_labels_gcs_uri',
            field=models.CharField(
                blank=True, default='', max_length=500,
                help_text='GCS path for the test ground-truth labels (kept separate from input data).',
            ),
        ),
    ]
