# Generated by Django 2.2.10 on 2020-08-05 15:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0025_auto_20200409_1112'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credentialapplication',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[('', '-----------'), (1, 'Reject'), (2, 'Accept'), (3, 'Withdrawn'), (4, 'Revoked')], default=0),
        ),
    ]
