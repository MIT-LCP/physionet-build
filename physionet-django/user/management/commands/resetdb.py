from django.core.management import call_command
from django.core.management.base import BaseCommand
import os
import shutil

from django.conf import settings
from project.models import Project


class Command(BaseCommand):

    def handle(self, *args, **options):
        project_apps = ['user', 'project']
        clear_db(project_apps)
        load_fixtures(project_apps)


def remove_migration_files(app):
    '''Remove all python migration files from registered apps'''
    app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
    if os.path.isdir(app_migrations_dir):
        migration_files = [file for file in os.listdir(app_migrations_dir) if file != '__init__.py' and file.endswith('.py')]
        for file in migration_files:
            os.remove(os.path.join(app_migrations_dir, file))

def clear_db(project_apps):
    """
    Delete the database and migration files.
    Remake and reapply the migrations
    """
    for app in project_apps:
        remove_migration_files(app)

    # delete the database
    db_file = os.path.join(settings.BASE_DIR, 'db.sqlite3')
    if os.path.isfile(db_file):
        os.remove(db_file)

    # Remake and reapply the migrations
    call_command('makemigrations')
    call_command('migrate')


def load_fixtures(project_apps):
    """
    Insert the demo content from each app's fixtures files.

    Demo Profile objects are located in a separate user_profiles.json fixture
    file as they can only be attached after the triggered profiles created
    are removed.
    """
    for app in project_apps:
        call_command('loaddata', app, verbosity=1)
