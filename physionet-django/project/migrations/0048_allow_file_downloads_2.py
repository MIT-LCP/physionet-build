from django.db import migrations, models


class Migration(migrations.Migration):
    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('project', '0047_allow_file_downloads_1'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activeproject',
            name='allow_file_downloads',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='archivedproject',
            name='allow_file_downloads',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='publishedproject',
            name='allow_file_downloads',
            field=models.BooleanField(default=True),
        ),
    ]
