from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('project', '0091_backfill_public_project_uuid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='publishedproject',
            name='public_project_uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text='Persistent, public identifier for published projects.',
                unique=True,
            ),
        ),
    ]
