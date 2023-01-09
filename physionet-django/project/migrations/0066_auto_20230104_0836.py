# Generated by Django 3.1.14 on 2023-01-04 13:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0065_editor_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='activeproject',
            name='allow_short_term_training',
            field=models.BooleanField(default=False, null=True),
        ),
        migrations.AddField(
            model_name='archivedproject',
            name='allow_short_term_training',
            field=models.BooleanField(default=False, null=True),
        ),
        migrations.AddField(
            model_name='publishedproject',
            name='allow_short_term_training',
            field=models.BooleanField(default=False, null=True),
        ),
    ]
