"""
Command to:
- delete all content from the database
- apply migrations
- delete all non-project media and static content

Does NOT load any data. This should generally only be used in
development environments.

Reference: https://code.djangoproject.com/ticket/23833

"""
import os
import shutil
import sys

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from lightwave.views import DBCAL_FILE
from project.models import ActiveProject, PublishedProject
from user.models import User, CredentialApplication


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--load-demo', '--loaddemo', action='store_true',
            help='Load demo project data after clearing the DB')

    def handle(self, *args, **options):
        # If not in development, prompt warning messages twice
        if 'development' not in settings.ENVIRONMENT:
            warning_messages = ['You are NOT in the development environment. Are you sure you want to reset the database and file content? [y/n]',
                                'All database content and non-project media/static content will be deleted. Are you sure? [y/n]',
                                'Final warning. Are you ABSOLUTELY SURE? [y/n]']
            for i in range(3):
                choice = input(warning_messages[i]).lower()
                if choice != 'y':
                    sys.exit('Exiting from reset. No actions applied.')
            print('Continuing reset')
        else:
            db_type = settings.DATABASES['default']['ENGINE'].split('.')[-1]

            if db_type == 'sqlite3':
                # For sqlite, just delete the file
                db_file = settings.DATABASES['default']['NAME']
                if os.path.isfile(db_file):
                    os.remove(db_file)
            elif db_type == 'postgresql':
                # Drop the database that holds all the tables and recreate it
                db = settings.DATABASES['default']
                sudo = shutil.which('sudo')

                if sudo is not None:
                    drop_command = 'sudo -u postgres dropdb --if-exists {name}'
                    create_command = 'sudo -u postgres createdb -O {user} {name}'
                else:
                    drop_command = 'PGPASSWORD=$DB_PASSWORD dropdb -h {host} -U {user} --if-exists {name}'
                    create_command = 'PGPASSWORD=$DB_PASSWORD createdb -h {host} -U {user} -O {user} {name}'

                os.system(drop_command.format(host=db['HOST'], user=db['USER'], name=db['NAME']))
                os.system(create_command.format(host=db['HOST'], user=db['USER'], name=db['NAME']))
            else:
                sys.exit('Unable to reset database of type: {}'.format(db_type))

        # Remove all media files
        clear_media_files()
        # Remove created static files
        clear_created_static_files()
        print('Removed all media files and targeted static files.')
        # Remove dbcal symlnk
        if os.path.islink(DBCAL_FILE):
            os.unlink(DBCAL_FILE)

        # Re-apply migrations
        call_command('migrate')

        # Load demo database content and files
        if options['load_demo']:
            call_command('loaddemo')


def clear_media_files():
    """
    Remove all media files.

    Removes all content in the media root, excluding the immediate
    subfolders themselves and the .gitkeep files.
    """
    for subdir in os.listdir(settings.MEDIA_ROOT):
        media_subdir = os.path.join(settings.MEDIA_ROOT, subdir)
        subdir_items = [os.path.join(media_subdir, item) for item in os.listdir(media_subdir) if item != '.gitkeep']
        for item in subdir_items:
            for root, dirs, files in os.walk(item):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o755)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o755)

            shutil.rmtree(item)

def clear_created_static_files():
    """
    Clear all the static files created.

    This function relies on targeted input directories, as opposed to
    `clear_media_files` which can clean all immediate subdirectories.

    """
    effective_static_root = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATICFILES_DIRS[0]

    for subdir in ['published-projects']:
        static_subdir = os.path.join(effective_static_root, subdir)
        subdir_items = [os.path.join(static_subdir, item) for item in os.listdir(static_subdir) if item != '.gitkeep']
        for item in subdir_items:
            for root, dirs, files in os.walk(item):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o755)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o755)

            shutil.rmtree(item)
