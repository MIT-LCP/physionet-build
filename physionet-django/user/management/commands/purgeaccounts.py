import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from user.models import User, AssociatedEmail, Profile

LOGGER = logging.getLogger(__name__)


def _display_name(user):
    # Accounts created without a Profile must stay purgeable, not crash the run.
    try:
        return user.get_full_name()
    except Profile.DoesNotExist:
        return '(no profile)'


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        Delete all user accounts and associated emails after 3 days of
        creation if they were not activated.
        """
        today = timezone.now()
        limit = today - timezone.timedelta(days=3)
        user_list = User.objects.filter(is_active=False, join_date__lt=limit)
        deleted = []
        for user in user_list:
            deleted.append("\n - Username: {0}\n   Email: {1}\n   Full Name: "
                           "{2}".format(user.username, user.email,
                                        _display_name(user)))
            user.delete()

        if deleted:
            LOGGER.info("The following accounts were removed:")
            for line in deleted:
                LOGGER.info(line)
        LOGGER.info("Total accounts removed {}".format(len(deleted)))

        associated_email_list = AssociatedEmail.objects.filter(
            is_verified=False, added_date__lt=limit, user__is_active=True)
        deleted = []

        for associated_email in associated_email_list:
            deleted.append("\n - Email: {0}\n   Belonged to: {1}\n   Username:"
                           " {2}".format(associated_email.email,
                                         _display_name(associated_email.user),
                                         associated_email.user.username))
            associated_email.delete()

        if deleted:
            LOGGER.info("The following associated emails were removed:")
            for line in deleted:
                LOGGER.info(line)
        LOGGER.info("Total associated emails removed {}".format(len(deleted)))
