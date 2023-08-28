import email.utils
import functools
import operator
import sys
import textwrap

from django.core.management.base import BaseCommand
from django.db.models import Q
import html2text

from project.models import ActiveProject, SubmissionStatus
from user.models import AssociatedEmail, User


def text_match(field, pattern):
    """
    Convert a glob-like search pattern to a Q object.

    Examples:

    >>> text_match("title", "foo")
    <Q: (AND: ('title__iexact', 'foo'))>

    >>> text_match("title", "foo*")
    <Q: (AND: ('title__istartswith', 'foo'))>

    >>> text_match("title", "*foo")
    <Q: (AND: ('title__iendswith', 'foo'))>

    >>> text_match("title", "*foo*")
    <Q: (AND: ('title__icontains', 'foo'))>

    Note that if there are multiple terms separated by '*', they can
    appear in any order:

    >>> text_match("title", "*foo*bar*")
    <Q: (AND: ('title__icontains', 'foo'), ('title__icontains', 'bar'))>
    """
    parts = pattern.split('*')
    if len(parts) == 1:
        return Q(**{field + '__iexact': pattern})
    constraints = []
    if parts[0]:
        constraints.append(Q(**{field + '__istartswith': parts[0]}))
    for p in parts[1:-1]:
        constraints.append(Q(**{field + '__icontains': p}))
    if parts[-1]:
        constraints.append(Q(**{field + '__iendswith': parts[-1]}))
    return functools.reduce(operator.and_, constraints)


class Command(BaseCommand):
    """
    Management command to list active projects in a simple table format.
    """
    def add_arguments(self, parser):
        parser.add_argument(
            '--title', '-t', metavar='TITLE',
            help='Search for project title (may include * wildcards)')
        parser.add_argument(
            '--author', '-a', metavar='NAME',
            help='Search for project author (may include * wildcards)')
        parser.add_argument(
            '--unsubmitted',
            action='store_true',
            help='Display unsubmitted projects')

    def handle(self, *args, **options):
        projects = ActiveProject.objects
        if options['unsubmitted']:
            projects = projects.filter(submission_status__lt=SubmissionStatus.NEEDS_ASSIGNMENT)
            order = 'creation_datetime'
        else:
            projects = projects.filter(submission_status__gte=SubmissionStatus.NEEDS_ASSIGNMENT)
            order = 'submission_datetime'

        if options['title']:
            projects = projects.filter(text_match('title', options['title']))

        if options['author']:
            emails = AssociatedEmail.objects.filter(is_verified=True).filter(
                text_match('email', options['author']))
            users = User.objects.filter(
                Q(associated_emails__in=emails)
                | text_match('username', options['author'])
                | text_match('profile__first_names', options['author'])
                | text_match('profile__last_name', options['author']))

            projects = projects.filter(authors__user__in=users)

        projects = projects.order_by(order, 'id')

        if sys.stdout.isatty():
            def nowrap(x):
                return '\033[?7l{} \033[?7h'.format(x)
        else:
            def nowrap(x):
                return str(x)

        try:
            prev_id = None
            for project in projects:
                # This query can sometimes return the same project
                # multiple times (e.g., once for each matching author.)
                # This might be a bug in Django or I might be
                # misunderstanding something.
                if project.id == prev_id:
                    continue
                prev_id = project.id

                status = str(project.submission_status).rjust(2)
                slug = project.slug
                if options['unsubmitted']:
                    date = project.creation_datetime.strftime('%Y-%m-%d')
                else:
                    date = project.submission_datetime.strftime('%Y-%m-%d')
                username = project.submitting_author().user.username
                title = project.title

                if options['verbosity'] < 1:
                    print('{}  {}'.format(slug, nowrap(title)))
                elif options['verbosity'] < 2:
                    print('{}  {}  {}  {}  {}'.format(
                        slug, status, date, username, nowrap(title)))
                else:
                    print('{}  {}  {}  {}'.format(
                        slug, status, date, username))

                    print('        Title:\t' + '\n\t\t'.join(
                        textwrap.wrap(title, 60)))

                    print('      Authors:\t' + ',\n\t\t'.join(
                        email.utils.formataddr((name, addr))
                        for (addr, name) in project.author_contact_info()))

                if options['verbosity'] >= 3:
                    abstract = html2text.html2text(project.abstract,
                                                   bodywidth=60)
                    print()
                    print(textwrap.indent(abstract, '\t\t').rstrip('\n'))
                    print()

        except BrokenPipeError:
            sys.exit(1)
