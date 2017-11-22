from django.core.management import call_command
from django.core.management.base import BaseCommand
import os

from physionet import settings
from user.models import User


class Command(BaseCommand):

    def handle(self, *args, **options):
        installed_apps = [a for a in settings.INSTALLED_APPS if not any(noncustom in a for noncustom in ['django', 'ckeditor'])]
        reset_db(installed_apps)
        load_fixtures(installed_apps)

def remove_migration_files(app):
    '''Remove all python migration files from registered apps'''
    app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
    if os.path.isdir(app_migrations_dir):
        migration_files = [file for file in os.listdir(app_migrations_dir) if file != '__init__.py' and file.endswith('.py')]
        for file in migration_files:
            os.remove(os.path.join(app_migrations_dir, file))

def reset_db(installed_apps):
        """
        Delete the database and migration files.
        Remake and reapply the migrations
        """
        for app in installed_apps:
            remove_migration_files(app)

        # delete the database
        db_file = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        if os.path.isfile(db_file):
            os.remove(db_file)

        # Remake and reapply the migrations
        call_command('makemigrations')
        call_command('migrate')

def load_fixtures(installed_apps):
    """
    Insert the demo content from each app's fixtures files.

    Demo Profile objects are located in a separate user_profiles.json fixture
    file as they can only be attached after the triggered profiles created
    are removed.
    """ 
    for app in installed_apps:
        call_command('loaddata', app, verbosity=1)





    

    




