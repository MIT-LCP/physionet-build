from django.core.management import call_command
from django.core.management.base import BaseCommand
import os

from physionet import settings
from user.models import User


class Command(BaseCommand):

    def handle(self, *args, **options):
        installed_apps = [a for a in settings.INSTALLED_APPS if not any(noncustom in a for noncustom in ['django', 'ckeditor'])]
        delete_db(installed_apps)
        load_fixtures(installed_apps)
        load_fixture_profiles()


def remove_migration_files(app):
    '''Remove all python migration files from registered apps'''
    app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
    if os.path.isdir(app_migrations_dir):
        migration_files = [file for file in os.listdir(app_migrations_dir) if file.startswith('0') and file.endswith('.py')]
        for file in migration_files:
            os.remove(os.path.join(app_migrations_dir, file))

def delete_db(installed_apps):
        """
        Delete the database and associated files
        """
        for app in installed_apps:
            remove_migration_files(app)

        # delete the database
        fn = 'db.sqlite3'
        try:
            os.remove(os.path.join(settings.BASE_DIR, fn))
        except:
            pass

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

def load_fixture_profiles():
    """
    Remove empty profiles attached to demo users from triggers.
    Load profile information from fixtures and attach them to users.
    """
    for user in User.objects.all():
        user.profile.delete()

    call_command('loaddata', 'user_profiles', verbosity=1)





    

    




