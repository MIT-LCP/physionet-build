# Generated by Django 3.2.16 on 2023-03-15 17:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0008_alter_event_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='event_agreement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    to='events.eventagreement'),
        ),
    ]
