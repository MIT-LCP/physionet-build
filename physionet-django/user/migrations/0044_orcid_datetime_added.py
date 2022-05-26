from django.db import migrations, models
import django.utils.timezone
from datetime import datetime, timedelta


def migrate_forward(apps, schema_editor):
    orcid_model = apps.get_model('user', 'Orcid')
    for row in orcid_model.objects.all():
        row.datetime_added = datetime.fromtimestamp(row.token_expiration) - timedelta(days = 20 * 365.2422)
        row.save()


def migrate_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0043_auto_20220406_1229'),
    ]

    operations = [
        migrations.AddField(
            model_name='orcid',
            name='datetime_added',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
