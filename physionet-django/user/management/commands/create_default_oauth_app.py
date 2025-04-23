from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth import get_user_model
from oauth2_provider.models import get_application_model


class Command(BaseCommand):
    help = 'Creates the default OAuth application for the given superuser.'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='The username of the superuser who will own the OAuth application.'
        )

    def handle(self, *args, **options):
        Application = get_application_model()
        User = get_user_model()

        username = options['username']
        try:
            user = User.objects.get(username=username, is_superuser=True)
        except User.DoesNotExist:
            raise CommandError(f'Superuser with username "{username}" does not exist.')

        app_name = getattr(settings, 'OAUTH_CLIENT_APP_NAME', 'Default OAuth Application')
        client_type = Application.CLIENT_CONFIDENTIAL
        authorization_grant_type = Application.GRANT_PASSWORD

        app, created = Application.objects.get_or_create(
            name=app_name,
            defaults={
                'user': user,
                'client_type': client_type,
                'authorization_grant_type': authorization_grant_type,
                'skip_authorization': True,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created OAuth application: {app.name}'))
        else:
            self.stdout.write(self.style.WARNING(f'OAuth application "{app.name}" already exists.'))
