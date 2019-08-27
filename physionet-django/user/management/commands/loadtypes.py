"""
Command to:
- reset and load fixtures for project structures
"""
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        # Load project types
        project_types_fixtures = os.path.join(settings.BASE_DIR, 'project',
                                          'fixtures', 'project-types.json')
        call_command('loaddata', project_types_fixtures, verbosity=1)