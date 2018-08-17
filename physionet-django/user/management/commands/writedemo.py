from django.core.management import call_command
from django.core.management.base import BaseCommand
import os

from django.conf import settings

from physionet.utility import get_project_apps


class Command(BaseCommand):
    """
    For each app, write the fixture data into demo fixture files
    """

    def handle(self, *args, **options):
        project_apps = get_project_apps()

        for app in project_apps:
            fixture_file = os.path.join(settings.BASE_DIR, app, 'fixtures', 'demo-%s.json' % app)
            call_command('dumpdata', app, natural_foreign=True, indent=2,
                output=fixture_file)
