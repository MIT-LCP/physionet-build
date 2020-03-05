import logging
from datetime import date

from django.core.management.base import BaseCommand

from user.models import User

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        For each app, write the fixture data
        """
        user_list = User.objects.filter(is_active=False)
        today = date.today()
        deleted = []
        for user in user_list:
            dates = today - user.join_date
            if dates.days >= 7:
                deleted.append(" - Username: {0}\n   Email: {1}\n   "
                               "Full Name: {2}".format(user.username,
                                                       user.email,
                                                       user.get_full_name()))
                user.delete()
        LOGGER.info("The following accounts were removed:")
        for line in deleted:
            print(line)
        LOGGER.info("Total accounts removed {}".format(len(deleted)))
