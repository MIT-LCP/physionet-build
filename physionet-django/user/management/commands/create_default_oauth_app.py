from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from oauth2_provider.models import get_application_model
from django.contrib.auth import get_user_model


def create_default_oauth_application(user=None, stdout=None):
    app_name = getattr(settings, "OAUTH_CLIENT_APP_NAME", "PhysioNet Client")
    Application = get_application_model()
    User = get_user_model()

    if not user:
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            msg = "No superuser found; skipping OAuth application creation."
            if stdout:
                stdout.write(msg)
            else:
                print(msg)
            return

    app, created = Application.objects.get_or_create(
        name=app_name,
        defaults={
            'user': user,
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
            'skip_authorization': True,
        }
    )

    msg = (
        f"Created OAuth application: {app.name}"
        if created else
        f'OAuth application "{app.name}" already exists.'
    )
    if stdout:
        stdout.write(msg)
    else:
        print(msg)


class Command(BaseCommand):
    help = 'Creates the default OAuth application.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Optional superuser username to assign as the application owner.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options.get("username")

        user = None
        if username:
            try:
                user = User.objects.get(username=username, is_superuser=True)
            except User.DoesNotExist:
                raise CommandError(f'Superuser with username "{username}" does not exist.')

        create_default_oauth_application(user=user, stdout=self.stdout)
