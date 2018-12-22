"""
Command to:
- delete all data from tables
- drop all tables
- delete migrations
- make migrations
- apply migrations

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

from physionet.utility import get_project_apps
from project.models import ActiveProject, PublishedProject, ArchivedProject
from user.models import User, CredentialApplication


class Command(BaseCommand):

    def handle(self, *args, **options):
        # If not in development, prompt warning messages twice
        if 'development' not in os.environ['DJANGO_SETTINGS_MODULE']:
            warning_messages = ['You are NOT in the development environment. Are you sure you want to reset the database? [y/n]',
                                'All the data will be removed, and existing migration files will be deleted. Are you sure? [y/n]',
                                'Final warning. Are you ABSOLUTELY SURE? [y/n]']
            for i in range(3):
                choice = input(warning_messages[i]).lower()
                if choice != 'y':
                    sys.exit('Exiting from reset. No actions applied.')
            print('Continuing reset')
        else:
            db_file = os.path.join(settings.BASE_DIR, 'db.sqlite3')
            if os.path.isfile(db_file):
                os.remove(db_file)

        project_apps = get_project_apps()

        for app in project_apps:
            migration_files = get_migration_files(app)
            if migration_files:
                # Reverse the migrations, which drops the tables. Only
                # works if migration files exist, regardless of
                # table/migration status. Equivalent of deleting
                # sqlite file.
                if 'development' not in os.environ['DJANGO_SETTINGS_MODULE']:
                    call_command('migrate', app, 'zero', verbosity=1)
                # Delete the migration .py files
                for file in migration_files:
                    os.remove(file)

        # Remove all media files
        clear_media_files()
        # Remove created static files
        clear_created_static_files()
        print('Removed all media files and targeted static files.')

        # Remake and apply the migrations
        call_command('makemigrations')
        call_command('migrate')


def get_migration_files(app):
    """
    Get all migration files for an app. Full path. Gets all .py files
    from the app's `migrations` directory.

    """
    app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
    if os.path.isdir(app_migrations_dir):
        migration_files = [os.path.join(app_migrations_dir, file) for file in os.listdir(app_migrations_dir) if file != '__init__.py' and file.endswith('.py')]
    else:
        migration_files = []

    return migration_files

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
            shutil.rmtree(item)
