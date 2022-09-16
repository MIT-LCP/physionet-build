# Management Command to compile static Sass files
import os
from django.core.management.base import BaseCommand, CommandError
from decouple import config
from django.core.management import call_command


def theme_generator(dark, primary):
    # creating the theme file
    with open('static/bootstrap/scss/theme.scss', 'w') as f:
        # cleaning the current contents of the file
        f.truncate(0)
        # writing the new contents to the file
        f.write('$theme-colors: (\n')
        f.write('"primary" : ' + primary + ',\n')
        f.write('"dark" : ' + dark + ',\n')
        f.write(');\n')
        f.write('@import "bootstrap"\n')


class Command(BaseCommand):
    help = 'Compile static Sass files'

    def handle(self, *args, **options):

        # getting the environment variables
        dark = config('DARK', default='#343A40')
        if len(dark) != 7:
            raise CommandError('DARK environment variable is not a valid hex color')

        primary = config('PRIMARY', default='#002A5C')
        if len(primary) != 7:
            raise CommandError('PRIMARY environment variable is not a valid hex color')

        # calling the theme generator function
        theme_generator(dark, primary)
        # calling the compile static command
        call_command('sass', 'static/bootstrap/scss/theme.scss', 'static/bootstrap/css/bootstrap.css')

        # writing the success message
        self.stdout.write(self.style.SUCCESS('Successfully compiled static Sass files'))
