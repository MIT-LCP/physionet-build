"""
Command to:
- load all fixtures named 'demo-*.*'
- create copy the demo media files

This should only be called in a clean database, such as after
`resetdb` is run. This should generally only be used in
development environments.

"""
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

class Command(BaseCommand):

    def handle(self, *args, **options):
        # If not in development, prompt warning messages twice
        if 'development' not in settings.ENVIRONMENT:
            warning_messages = ['You are NOT in the development environment. Are you sure you want to insert demo data? [y/n]',
                                'The demo data will be mixed with existing data. Are you sure? [y/n]',
                                'Final warning. Are you ABSOLUTELY SURE? [y/n]']
            for i in range(3):
                choice = input(warning_messages[i]).lower()
                if choice != 'y':
                    sys.exit('Exiting from load. No actions applied.')
            print('Continuing loading demo data')

        # Load licences and software languages
        sections_fixtures = os.path.join(settings.BASE_DIR, 'physionet',
                                    'fixtures', 'steps.json')
        call_command('loaddata', sections_fixtures, verbosity=1)