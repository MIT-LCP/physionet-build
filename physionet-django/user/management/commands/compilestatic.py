# Management Command to compile static Sass files
import os
import urllib.request
import urllib.error
from django.core.management.base import BaseCommand, CommandError
from decouple import config
from django.core.management import call_command


def theme_generator(themes_colors, imports=['bootstrap']):
    # creating the theme file
    with open('static/bootstrap/scss/theme.scss', 'w') as f:
        # cleaning the current contents of the file
        f.truncate(0)
        # writing the new contents to the file
        f.write('$theme-colors: (\n')
        for key, value in themes_colors.items():
            f.write(f'"{key}" : {value},\n')
        f.write(');\n')
        for imp in imports:
            f.write(f'@import "{imp}";\n')


def setup_theme_colors(colors):
    """
    Setups a map of theme colors from environment variables, validates them and returns a dictionary
    :param colors: a map of colors to be set
    :return: a dictionary of theme colors
    """
    themes_colors = {}
    for key, value in colors.items():
        value = config(key, default=value)
        if len(value) != 7 and value[0] == '#':
            raise CommandError(f'{key} environment variable is not a valid hex color')
        themes_colors[key.lower()] = value
    return themes_colors


def setup_static_file(source, destination):
    """
    Copies a static file from source to destination
    :param source: the source file path(direct url)
    :param destination: the destination file path
    """

    try:
        urllib.request.urlretrieve(source, destination)
    except urllib.error.HTTPError:
        raise CommandError(f'Could not download {source}')
    except urllib.error.URLError:
        raise CommandError(f'Could not download {source}')


class Command(BaseCommand):
    help = 'Compile static Sass files'

    def handle(self, *args, **options):

        # getting the environment variables
        colors = {
            'DARK': '#343A40',
            'PRIMARY': '#002A5C',
            'SECONDARY': '#6C757D',
            'SUCCESS': '#28A745',
            'INFO': '#17A2B8',
            'WARNING': '#FFC107',
            'DANGER': '#DC3545',
            'LIGHT': '#F8F9FA',
            'GRADIENT_60': 'rgba(42, 47, 52, 0.6)',
            'GRADIENT_85': 'rgba(42, 47, 52, 0.85)',
        }
        themes_colors = setup_theme_colors(colors)

        # calling the theme generator function
        theme_generator(themes_colors)
        # calling the compile static command
        call_command('sass', 'static/bootstrap/scss/theme.scss', 'static/bootstrap/css/bootstrap.css')

        # writing the success message
        self.stdout.write(self.style.SUCCESS('Successfully compiled static Sass files'))

        # setup background image
        image_source = config('BACKGROUND_IMAGE', default='https://physionet.org/static/images/background.jpg')
        image_destination = 'static/images/background.jpg'
        setup_static_file(image_source, image_destination)
        self.stdout.write(self.style.SUCCESS('Successfully setup background image'))

        # Demo section for home.css
        theme_generator(themes_colors, imports=['../../custom/scss/home'])
        call_command('sass', 'static/bootstrap/scss/theme.scss', 'static/custom/css/home.css')
