from django.core.management import call_command, execute_from_command_line
from django.core.management.base import BaseCommand, CommandError
from django.core.management.commands import loaddata
import os

from physionet import settings
from user.models import User, Profile



class Command(BaseCommand):

    def handle(self, *args, **options):
        installed_apps = [a for a in settings.INSTALLED_APPS if not any(noncustom in a for noncustom in ['django', 'ckeditor'])]
        self.deletedb(installed_apps)
        self.createusers(installed_apps)
        self.loadfixtures(installed_apps)


    def remove_migration_files(self,app):
        '''Remove all python migration files from registered apps'''
        app_migrations_dir = os.path.join(settings.BASE_DIR, app, 'migrations')
        if os.path.isdir(app_migrations_dir):
            migration_files = [file for file in os.listdir(app_migrations_dir) if file.startswith('0') and file.endswith('.py')]
            for file in migration_files:
                os.remove(os.path.join(app_migrations_dir, file))

    def deletedb(self,installed_apps):
        """
        Delete the database and associated files
        """
        for app in installed_apps:
            self.remove_migration_files(app)

        # delete the database
        fn = 'db.sqlite3'
        try:
            os.remove(os.path.join(settings.BASE_DIR, fn))
        except:
            pass

        # Remake and reapply the migrations
        execute_from_command_line(['manage.py', 'makemigrations'])
        execute_from_command_line(['manage.py', 'migrate'])

    def createusers(self,installed_apps):
        """
        Create some demo users
        """
        user0 = User.objects.create_superuser(email="tester@mit.edu", password="Tester1!")
        user1 = User.objects.create_user(email="rgmark@mit.edu", password="Tester1!", is_active=True)
        user2 = User.objects.create_user(email="george@mit.edu", password="Tester1!", is_active=True)
        # Delete the empty profiles created from triggers
        user0.profile.delete()
        user1.profile.delete()
        user2.profile.delete()


    def loadfixtures(self,installed_apps):
        """
        Insert the demo content from the fixtures files
        """ 
        for app in installed_apps:
            app_fixtures_dir = os.path.join(settings.BASE_DIR, app, 'fixtures')
            call_command('loaddata', app, verbosity=1)


