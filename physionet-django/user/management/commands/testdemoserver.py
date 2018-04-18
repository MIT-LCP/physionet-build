"""
Command to run the test server with the content from the demo fixtures.
Just calls 'testserver' command with the appropriate fixture paths.

"""
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        project_apps = ['user', 'project']
        demo_fixtures = [os.path.join(settings.BASE_DIR, app, 'fixtures',
                                      'demo-%s.json' % app)
                         for app in project_apps]
        call_command('testserver', *demo_fixtures)
