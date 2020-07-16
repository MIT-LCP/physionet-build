"""
Command to:
- Parse NGINX log files and write their metrics data to the database
"""

import os
import time
import datetime
import hashlib
import warnings

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import make_aware

from project.models import CoreProject, PublishedProject, Metrics, MetricsLogData


class Command(BaseCommand):
    """
    Command to parse one or more log files and load data to the Metrics table.
    """
    help = "Parses one or more log files and loads data to the Metrics table."

    def add_arguments(self, parser):
        parser.add_argument('files', nargs='+', type=str,
                            help='Specify log file(s) to parse')

    def handle(self, *args, **options):
        """Retrieves metrics data from the latest log file, or as specified.

        Retrieves view count from most recent log file, or from the log file(s)
            specified in **options.

        Args:
            **options:
                files [filename(s)]: One or more NGINX log file(s) to parse.

        Returns:
            None

        Raises:
            InvalidLogError: An error occurred obtaining metrics data from the
                log file.
        """
        files = options['files']

        for filename in files:
            if check_log_hash(filename) is True:
                warnings.warn(f'Log file {filename} has already been parsed',
                              UserWarning)
                continue
            try:
                validate_log_file(filename)
                unparsed_lines = update_metrics(filename)
                if unparsed_lines > 0:
                    warnings.warn(f'This file has {unparsed_lines} line(s) that could not be parsed', UserWarning)
            except InvalidLogError:
                raise InvalidLogError(
                    f'Log file {filename} is not a valid NGINX log')


def check_log_hash(filename):
    """Checks if a given file has been parsed before.

    Hashes the given file to check if it has already been parsed before.

    Args:
        filename: An NGINX log file to parse.

    Returns:
        bool: True if the file has been parsed before, False otherwise.
    """
    BLOCK_SIZE = 65536

    file_hash = hashlib.sha256()
    with open(filename, 'rb') as f:
        fb = f.read(BLOCK_SIZE)
        while len(fb) > 0:
            file_hash.update(fb)
            fb = f.read(BLOCK_SIZE)

    current_hash = file_hash.hexdigest()
    if MetricsLogData.objects.filter(log_hash=current_hash).exists():
        return True

    else:
        creation_datetime = make_aware(datetime.datetime.strptime(time.ctime(
            os.path.getctime(filename)), "%a %b %d %H:%M:%S %Y"))
        new_log = MetricsLogData.objects.create(filename=filename,
                                                creation_datetime=creation_datetime,
                                                log_hash=current_hash)
        new_log.save()
        return False


def validate_log_file(filename):
    """Checks if a log file is a valid NGINX log.

    Checks if the given file has slug, date, and IP address in the correct
        location.

    Args:
        filename: An NGINX log file to parse.

    Returns:
        None

    Raises:
        InvalidLogError: An error occurred obtaining date data from the log
            file.
    """
    with open(filename) as f:
        first_line = f.readline()
        split_line = first_line.split()
        try:
            if 'GET' in split_line[5] and (
                    '/files/' in split_line[6]
                    or '/content/' in split_line[6]):
                path = split_line[6].split('?')[0]
                slug = path.split('/')[2]
                date = datetime.datetime.strptime(split_line[3][1:12],
                                                  "%d/%b/%Y")
                ip = split_line[0]
        except IndexError:
            raise InvalidLogError


def update_metrics(filename):
    """Updates project metrics in the database.

    Obtains metrics data from log_parser and then updates each core project
    with new data.

    Args:
        filename: An NGINX log file to parse.

    Returns:
        An int representing the number of lines in the file that could not
            be parsed.
    """
    log_data, unparsed_lines = log_parser(filename)

    for p in PublishedProject.objects.filter(is_latest_version=True):
        if p.slug in log_data:
            update_count = 0
            update_date = datetime.datetime.min
            for date in log_data[p.slug]:
                update_count += log_data[p.slug][date][0]
                if update_date < date:
                    update_date = date
            try:
                last_entry = Metrics.objects.filter(
                    core_project=p.core_project).latest('date')
            except ObjectDoesNotExist:
                last_entry = None
            project = Metrics.objects.create(
                core_project=p.core_project,
                date=update_date)
            if last_entry:
                project.running_viewcount = last_entry.running_viewcount
            project.viewcount = update_count
            project.running_viewcount += update_count
            project.save()
    return unparsed_lines


def log_parser(filename):
    """Parses an NGINX log file to extract metrics data.

    Generates view counts per project per date based on log data.

    Args:
        filename: An NGINX log file to parse.

    Returns:
        A dict mapping project slugs to their respective project view date,
        count, and set of IP addresses. For example:

        {'demoecg': {datetime.datetime(2020, 7, 3, 0, 0): [1,
            {'133.229.30.163'}], datetime.datetime(2020, 7, 4, 0, 0): [2,
            {'62.83.94.91', '133.229.30.163'}]},
        'demoeicu': {datetime.datetime(2020, 7, 4, 0, 0): 1,
            {'154.158.105.50'}]},
        'demopsn': {datetime.datetime(2020, 7, 4, 0, 0): 1,
            {'110.148.237.169'}]}}

        An int representing the number of lines in the file that could not
            be parsed.
    """
    data = {}
    unparsed_lines = 0

    with open(filename) as file:
        for line in file:
            parts = line.split()
            try:
                if 'GET' in parts[5] and (
                        '/files/' in parts[6] or '/content/' in parts[6]):
                    path = parts[6].split('?')[0]
                    slug = path.split('/')[2]
                    date = datetime.datetime.strptime(parts[3][1:12], "%d/%b/%Y")
                    ip = parts[0]
                    if slug not in data:
                        data[slug] = {date: [0, set()]}
                    elif date not in data[slug]:
                        data[slug][date] = [0, set()]
                    if ip not in data[slug][date][1]:
                        data[slug][date][0] += 1
                        data[slug][date][1].add(ip)
            except IndexError:
                unparsed_lines += 1
        return data, unparsed_lines


class Error(Exception):
    pass


class InvalidLogError(Error):
    """Exception raised for invalid NGINX log file"""
    pass
