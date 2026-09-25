from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0005_add_official_start_datetime'),
    ]

    operations = [
        migrations.AddField(
            model_name='challengeconfiguration',
            name='organizer_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='challenge',
            name='organizer_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
