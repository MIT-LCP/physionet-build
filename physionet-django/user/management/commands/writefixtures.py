from django.core.management import call_command
from django.core.management.base import BaseCommand
import os
import shutil

from physionet import settings
from project.models import Project


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        For each app, write the fixture data
        """
        installed_apps = [a for a in settings.INSTALLED_APPS if not any(noncustom in a for noncustom in ['django', 'ckeditor'])]

        for app in installed_apps:
            fixture_file = os.path.join(settings.BASE_DIR, app, 'fixtures', '%s.json' % app)
            call_command('dumpdata', app, natural_foreign=True, indent=2,
                output=fixture_file)
