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

from project.models import Project


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

        project_apps = ['user', 'project']
        # Delete the project objects so that their directories get
        # cleared. Only needs to run if migrations have been applied.
        try:
            Project.objects.all().delete()
        except:
            pass

        # Remove data from all tables. Tables are kept.
        call_command('flush', interactive=False, verbosity=1)

        for app in project_apps:
            # Reverse migrations, which drops the tables. Only works if
            # migration files exist, regardless of table/migration status.
            try:
                call_command('migrate', app, 'zero', verbosity=1)
            except:
                pass
            # Delete the migration .py files
            remove_migration_files(app)

        # Remake and apply the migrations
        call_command('makemigrations')
        call_command('migrate')


def remove_migration_files(app):
    """
    Remove all python migration files from an app

    """
    app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
    if os.path.isdir(app_migrations_dir):
        migration_files = [file for file in os.listdir(app_migrations_dir) if file != '__init__.py' and file.endswith('.py')]
        for file in migration_files:
            os.remove(os.path.join(app_migrations_dir, file))

