import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from oauth.device import delete_expired_device_grants
from user.models import PersonalAccessToken

LOGGER = logging.getLogger(__name__)

# Expired tokens stay listed on the settings page, marked as expired, for this
# many days so users can see why a script stopped working. Then they are
# deleted.
EXPIRED_TOKEN_DAY_LIMIT = 30


class Command(BaseCommand):
    help = (
        f"Delete personal access tokens that expired more than {EXPIRED_TOKEN_DAY_LIMIT} days ago, "
        "and expired device flow codes."
    )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(days=EXPIRED_TOKEN_DAY_LIMIT)
        deleted_count, _ = PersonalAccessToken.objects.filter(expires__lt=cutoff).delete()
        LOGGER.info("Deleted %d expired personal access tokens", deleted_count)

        # Sign-ins also delete expired codes; this catches any left on a quiet site.
        deleted_count = delete_expired_device_grants()
        LOGGER.info("Deleted %d expired device flow codes", deleted_count)
