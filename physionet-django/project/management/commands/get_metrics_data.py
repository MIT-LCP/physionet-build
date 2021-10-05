"""
Command to:
- Parse NGINX log files and write their metrics data to the database
"""

import datetime
from distutils.util import strtobool

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from project.models import CoreProject, PublishedProject, Metrics


class Command(BaseCommand):
    """
    Command to parse a log file and load data to the Metrics table.
    """
    help = "Parses a log file and loads data to the Metrics table."

    def add_arguments(self, parser):
        parser.add_argument('files', nargs='+', type=str,
                            help='Specify log file(s) to parse')
        parser.add_argument('-c', '--check_date', type=strtobool,
                            default=False,
                            help='If True, checks if log date is day before '
                            'current date')
        parser.add_argument('-n', '--now', type=str, default=None,
                            help='Use given date as "now" (format DD/MM/YYYY)')

    def handle(self, *args, **options):
        """Retrieves metrics data from the latest log file, or as specified.

        Retrieves view count from most recent log file, or from the log file(s)
            specified in **options.

        Args:
            **options:
                files [filename(s)]: One or more NGINX log file(s) to parse.
                -c [bool]: If True, runs update from log as cron job.
                -n [date]: If running a cron job, treats the given date as
                    "now". Format: DD/MM/YYYY.

        Returns:
            None

        Raises:
            InvalidLogError: An error occurred obtaining metrics data from the
                log file.
            DateError: The date in the log file does not match the expected
                date (if run as a cron job, the log file date should be the day
                before).
        """
        files = options['files']
        check_date = options['check_date']
        now = options['now']

        if now is not None:
            now = datetime.datetime.strptime(now, "%d/%m/%Y")

        for filename in files:
            try:
                validate_log_file(filename, check_date, now)
                update_metrics(filename)
            except InvalidLogError:
                raise InvalidLogError(
                    f'Log file {filename} is not a valid NGINX log')
            except DateError:
                raise DateError('Log file has incorrect date')


def log_parser(filename):
    """Parses an NGINX log file to extract metrics data.

    Generates view counts per project based on log data.

    Args:
        filename: An NGINX log file to parse.

    Returns:
        A dict mapping project slugs to their respective project view date,
        count, and set of IP addresses. For example:

        {'demoecg': [datetime.datetime(2020, 7, 4, 0, 0), 2,
            {'62.83.94.91', '133.229.30.163'}],
        'demoeicu': [datetime.datetime(2020, 7, 4, 0, 0), 1,
            {'154.158.105.50'}],
        'demopsn': [datetime.datetime(2020, 7, 4, 0, 0), 1,
            {'110.148.237.169'}]}

    Raises:
        InvalidLogError: An error occurred obtaining metrics data from the log
            file.
        DateError: The date in the log file does not match the expected date
            (if run as a cron job, the log file date should be the day before).
    """
    my_file = open(filename).read()
    file_lines = my_file.split('\n')

    data = {}

    for line in file_lines:
        parts = line.split()
        try:
            if '?' not in parts[6] and 'GET' in parts[5] and (
                    '/files' in parts[6] or '/content' in parts[6]):
                split_slash = parts[6].split('/')
                slug = split_slash[2]
                date = datetime.datetime.strptime(parts[3][1:12], "%d/%b/%Y")
                ip = parts[0]
                if slug not in data:
                    data[slug] = [date, 0, set()]
                if ip not in data[slug][2]:
                    data[slug][1] += 1
                    data[slug][2].add(ip)
        except IndexError:
            if line:
                print("Invalid line in log:", line)
    return data


def update_metrics(filename):
    """Updates project metrics in the database.

    Obtains metrics data from log_parser and then updates each core project
    with new data.

    Args:
        filename: An NGINX log file to parse.

    Returns:
        None
    """
    log_data = log_parser(filename)

    for p in PublishedProject.objects.filter(is_latest_version=True):
        if p.slug in log_data:
            try:
                last_entry = Metrics.objects.filter(
                    core_project=p.core_project).latest('date')
                # Do not update if log file is older than latest entry
                if last_entry.date >= log_data[p.slug][0].date():
                    continue
            except ObjectDoesNotExist:
                last_entry = None
            project = Metrics.objects.create(
                core_project=p.core_project,
                date=log_data[p.slug][0])
            if last_entry:
                project.running_viewcount = last_entry.running_viewcount
            project.viewcount = log_data[p.slug][1]
            project.running_viewcount += log_data[p.slug][1]
            project.save()


def validate_log_file(filename, check_date=False, now=None):
    """Checks if a log file is a valid NGINX log and has correct date

    Checks if the given file has a date in the right place and format. If
        called during a cron job, checks if the log file's date is the day
        before the current date.

    Args:
        filename: An NGINX log file to parse.
        check_date: Optional; If True, checks if date is correct for cron job.
        now: Optional; If running cron job, treats this date as the currrent
            date instead of timezone.now().

    Returns:
        None

    Raises:
        InvalidLogError: An error occurred obtaining date data from the log
            file.
        DateError: The date in the log file does not match the expected date
            (if run as a cron job, the log file date should be the day before).
    """
    if now is None:
        now = timezone.now()

    with open(filename) as f:
        first_line = f.readline()
        split_line = first_line.split()
        try:
            str_date = split_line[3][1:12]
            log_date = datetime.datetime.strptime(str_date, "%d/%b/%Y")
        except LookupError:
            raise InvalidLogError

    if check_date:
        if not (now.day - 1 == log_date.day and now.month ==
                log_date.month and now.year == log_date.year):
            raise DateError
    return


class Error(Exception):
    pass


class InvalidLogError(Error):
    """Exception raised for invalid NGINX log file"""
    pass


class DateError(Error):
    """Exception raised during cron job when a log file's date is not the
        previous day's date"""
    pass
