from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0003_add_test_scoring_claim_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='test_scoring_error_message',
            field=models.TextField(
                blank=True, default='', db_default='',
                help_text='Official test scoring diagnostics, visible only to organizers.',
            ),
        ),
    ]
