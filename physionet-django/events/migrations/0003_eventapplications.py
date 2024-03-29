# Generated by Django 3.2.16 on 2023-02-06 18:50

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0002_alter_event_slug'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventApplication',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_datetime', models.DateTimeField(auto_now_add=True)),
                ('decision_datetime', models.DateTimeField(null=True)),
                ('comment_to_applicant', models.TextField(blank=True, default='', max_length=500)),
                ('status', models.CharField(
                    choices=[('WL', 'Waitlisted'), ('AP', 'Approved'), ('NA', 'Not Approved'), ('WD', 'Withdrawn')],
                    default='WL', max_length=2)
                 ),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='applications',
                                            to='events.event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
