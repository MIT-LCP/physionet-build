# Generated by Django 2.2.27 on 2022-02-28 19:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('physionet', '0002_auto_20220228_1217'),
    ]

    operations = [
        migrations.AlterField(
            model_name='section',
            name='static_page',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='physionet.StaticPage'),
        ),
        migrations.AlterUniqueTogether(
            name='section',
            unique_together={('static_page', 'order')},
        ),
        migrations.RemoveField(
            model_name='section',
            name='page',
        ),
    ]
