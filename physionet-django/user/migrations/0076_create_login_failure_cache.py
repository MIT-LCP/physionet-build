from django.core.management import call_command
from django.db import migrations

# Table for the 'login_failures' cache in settings.CACHES
TABLE = 'login_failure_cache'


def create_cache_table(apps, schema_editor):
    call_command('createcachetable', TABLE, database=schema_editor.connection.alias)


def drop_cache_table(apps, schema_editor):
    schema_editor.execute(schema_editor.sql_delete_table % {'table': schema_editor.quote_name(TABLE)})


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0075_credentialapplication_reference_user'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
