# Management Command to compile static Sass files

import os

from django.core.management.base import BaseCommand, CommandError

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

        dark = '#343A40'
        primary = '#002A5C'

        # checking if DARK environemnt variable is set
        if os.environ.get('DARK'):
            # setting the the Dark Parameter to the environment variable
            dark = '#' + str(os.environ.get('DARK'))
            # checking if the Dark Parameter is a valid hex color
            if len(dark) != 7:
                raise CommandError('DARK environment variable is not a valid hex color')
            # announcing the change
            self.stdout.write(self.style.SUCCESS('DARK environment variable set to %s' % dark))



        # checking if PRIMARY environemnt variable is set
        if os.environ.get('PRIMARY'):
            # setting the the Primary Parameter to the environment variable
            primary = '#' + str(os.environ.get('PRIMARY'))
            # checking if the Primary Parameter is a valid hex color
            if len(primary) != 7:
                raise CommandError('PRIMARY environment variable is not a valid hex color')
            # announcing the change
            self.stdout.write(self.style.SUCCESS('PRIMARY environment variable set to %s' % primary))


        try:
            # calling the theme generator function
            theme_generator(dark, primary)
            try:
                # compiling the static files
                os.system('python manage.py sass static/bootstrap/scss/ static/bootstrap/css/')
            except Exception as e:
                # printing the error message
                print(e)
                exit(1)            
            # writing the success message
            self.stdout.write(self.style.SUCCESS('Successfully compiled static Sass files'))
        except Exception as e:
            raise CommandError('Error compiling static files: %s' % e)        