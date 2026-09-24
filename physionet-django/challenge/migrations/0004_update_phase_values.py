from django.db import migrations, models


PHASE_MAP = {
    'setup': 'registration',
    'active': 'unofficial',
    'review': 'official',
    'completed': 'results',
}

REVERSE_PHASE_MAP = {v: k for k, v in PHASE_MAP.items()}


def convert_phases_forward(apps, schema_editor):
    Challenge = apps.get_model('challenge', 'Challenge')
    for old_val, new_val in PHASE_MAP.items():
        Challenge.objects.filter(phase=old_val).update(phase=new_val)


def convert_phases_backward(apps, schema_editor):
    Challenge = apps.get_model('challenge', 'Challenge')
    for new_val, old_val in REVERSE_PHASE_MAP.items():
        Challenge.objects.filter(phase=new_val).update(phase=old_val)


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0003_remove_challenge_dev_dataset_and_more'),
    ]

    operations = [
        migrations.RunPython(
            convert_phases_forward,
            convert_phases_backward,
        ),
        migrations.AlterField(
            model_name='challenge',
            name='phase',
            field=models.CharField(
                choices=[
                    ('registration', 'Registration'),
                    ('unofficial', 'Unofficial'),
                    ('official', 'Official'),
                    ('results', 'Results'),
                    ('archived', 'Archived'),
                ],
                default='registration',
                max_length=20,
            ),
        ),
    ]
