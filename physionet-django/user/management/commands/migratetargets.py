from django.db import DEFAULT_DB_ALIAS
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--database', default=DEFAULT_DB_ALIAS,
            help='Name of database')
        parser.add_argument(
            '--plan', action='store_true',
            help='Show a list of actions to perform')
        parser.add_argument(
            '--noinput', '--no-input', action='store_false',
            dest='interactive',
            help='Never prompt for input')
        parser.add_argument(
            '--reverse', action='store_true',
            help='Apply migrations in reverse order')
        parser.add_argument(
            'filename',
            help='name of file listing migrations to apply')

    def handle(self, *args, **options):
        migrations = []
        with open(options['filename'], 'r') as f:
            for l in f:
                (app, name) = l.split()
                migrations.append((app, name))

        if options['reverse']:
            migrations.reverse()

        for (app, name) in migrations:
            call_command('migrate', app_label=app,
                         migration_name=name,
                         database=options['database'],
                         plan=options['plan'],
                         interactive=options['interactive'],
                         verbosity=options['verbosity'])
