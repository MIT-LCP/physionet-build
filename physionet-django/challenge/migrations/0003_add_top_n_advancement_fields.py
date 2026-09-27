from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0002_alter_challengeconfiguration_additional_metrics_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='challengeconfiguration',
            name='max_submissions_to_advance',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Number of top submissions per participant/team to advance to test scoring.',
            ),
        ),
        migrations.AddField(
            model_name='challenge',
            name='max_submissions_to_advance',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Number of top submissions per participant/team to advance to test scoring.',
            ),
        ),
        migrations.AddField(
            model_name='submission',
            name='advanced_to_official',
            field=models.BooleanField(
                default=False,
                help_text='Whether this submission was selected for test scoring in the official phase.',
            ),
        ),
    ]
