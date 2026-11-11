import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from oauth2_provider.models import get_device_grant_model

from user.models import PersonalAccessToken

LOGGER = logging.getLogger(__name__)

# Expired tokens stay listed on the settings page, marked as expired, for this
# many days so users can see why a script stopped working. Then they are
# deleted.
EXPIRED_TOKEN_DAY_LIMIT = 30

# Device flow codes are only needed until they expire, after a few minutes.
EXPIRED_DEVICE_GRANT_DAY_LIMIT = 1


class Command(BaseCommand):
    help = (
        f"Delete personal access tokens that expired more than {EXPIRED_TOKEN_DAY_LIMIT} days ago, "
        f"and device flow codes that expired more than {EXPIRED_DEVICE_GRANT_DAY_LIMIT} day ago."
    )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(days=EXPIRED_TOKEN_DAY_LIMIT)
        deleted_count, _ = PersonalAccessToken.objects.filter(expires__lt=cutoff).delete()
        LOGGER.info("Deleted %d expired personal access tokens", deleted_count)

        cutoff = timezone.now() - timezone.timedelta(days=EXPIRED_DEVICE_GRANT_DAY_LIMIT)
        deleted_count, _ = get_device_grant_model().objects.filter(expires__lt=cutoff).delete()
        LOGGER.info("Deleted %d expired device flow codes", deleted_count)
