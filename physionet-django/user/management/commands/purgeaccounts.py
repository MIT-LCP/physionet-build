import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from user.models import User

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        Delete all user accounts after 7 days of creation if they were not
        activated.
        """
        today = date.today()
        limit = today - timedelta(days=7)
        user_list = User.objects.filter(is_active=False, join_date__lt=limit)
        deleted = []
        for user in user_list:
            dates = today - user.join_date
            deleted.append(" - Username: {0}\n   Email: {1}\n   Full Name: "
                           "{2}".format(user.username, user.email,
                                        user.get_full_name()))
            user.delete()

        LOGGER.info("The following accounts were removed:")
        for line in deleted:
            LOGGER.info(line)
        LOGGER.info("Total accounts removed {}".format(len(deleted)))
