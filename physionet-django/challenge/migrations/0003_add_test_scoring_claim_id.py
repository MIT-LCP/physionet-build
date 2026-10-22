from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0002_add_test_scoring_complete'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='test_scoring_claim_id',
            field=models.UUIDField(
                null=True, blank=True,
                help_text='Identifies the worker that owns the current test scoring claim.',
            ),
        ),
    ]
