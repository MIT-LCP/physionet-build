# Generated by Django 2.2.6 on 2020-02-14 21:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0038_auto_20200214_1559'),
    ]

    operations = [
        migrations.AlterField(
            model_name='editlog',
            name='auto_doi',
            field=models.BooleanField(default=True),
        ),
    ]
