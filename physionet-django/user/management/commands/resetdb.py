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

        # Clean the data
        call_command('flush', interactive=False)

        # This order is important because we need to reset the project
        # migrations first, which depend on user migrations.
        project_apps = ['project', 'user']

        for app in project_apps:
            migration_files = get_migration_files(app)
            if migration_files:
                # Reverse the migrations, which drops the tables. Only
                # works if migration files exist, regardless of
                # table/migration status.
                call_command('migrate', app, 'zero', verbosity=1)
                # Delete the migration .py files
                for file in migration_files:
                    os.remove(file)

        # Remove project files
        clear_project_files()
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

def clear_project_files():
    """
    Remove all project content from the root project directory
    """
    project_root = os.path.join(settings.MEDIA_ROOT, 'projects')

    project_items = [os.path.join(project_root, item) for item in os.listdir(project_root) if item != '.gitkeep']

    for item in project_items:
        if os.path.islink(item):
            os.unlink(item)
        elif os.path.isdir(item):
            shutil.rmtree(item)
