from django.core.management import call_command
from django.core.management.base import BaseCommand
import os

from django.conf import settings


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        For each app, write the fixture data
        """
        project_apps = ['user', 'project']

        for app in project_apps:
            fixture_file = os.path.join(settings.BASE_DIR, app, 'fixtures', '%s.json' % app)
            call_command('dumpdata', app, natural_foreign=True, indent=2,
                output=fixture_file)
