import os
from subprocess import call
from django.core.management import execute_from_command_line

from physionet import settings
from user.models import User


installed_apps = [a for a in settings.INSTALLED_APPS if 'django' not in a]

# Remove all python migration files from registered apps
for app in installed_apps:
    app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
    
    if os.path.isdir(app_migrations_dir):
        migration_files = [file for file in os.listdir(app_migrations_dir) if file.startswith('0') and file.endswith('.py')]
        for file in migration_files:
            os.remove(os.path.join(app_migrations_dir, file))

# Remove the database file
try:
    os.remove(os.path.join(settings.BASE_DIR, 'db.sqlite3'))
except:
    pass

# Remake and reapply the migrations
execute_from_command_line(['manage.py', 'makemigrations'])
execute_from_command_line(['manage.py', 'migrate'])

# Insert the demo content from the fixtures files
for app in installed_apps:
    app_fixtures_dir = os.path.join(settings.BASE_DIR, app, 'fixtures')
    if os.path.isdir(app_fixtures_dir) and os.path.isfile(os.path.join(app_fixtures_dir, app+'.json')):
        execute_from_command_line(['manage.py', 'loaddata', app])

# Create a superuser account
User.objects.create_superuser(email="tester@mit.edu", password="Tester1!")