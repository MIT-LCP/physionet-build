import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0012_notification'),
    ]

    operations = [
        migrations.AlterField(
            model_name='news',
            name='guid',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
