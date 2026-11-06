"""
Fill in the DOI of references whose citation already includes one.

References written before the DOI field existed often include the DOI
in the citation text, e.g. "... https://doi.org/10.13026/C2XW26". This
command copies such DOIs into the DOI field, so that they are linked
and included in the project's DOI metadata. The citation text is not
changed.

A reference is skipped, and listed, if its citation includes more
than one DOI, if the DOI is not valid, or if another reference in the
same project already has that DOI.

Usage:
    python manage.py backfill_reference_dois           # List the changes
    python manage.py backfill_reference_dois --apply   # Save them
"""
from collections import namedtuple
from itertools import groupby

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from project.models import PublishedReference, Reference
from project.validators import find_dois, validate_doi

Change = namedtuple('Change', 'reference doi')
Skip = namedtuple('Skip', 'reference reason')


def count(number, noun):
    return f'{number} {noun}' if number == 1 else f'{number} {noun}s'


def project_label(reference):
    project = reference.project
    if isinstance(reference, PublishedReference):
        return f'{project.slug} v{project.version}'
    return project.slug


def find_backfill(references, project_key):
    """
    Return the DOIs to fill in for a set of references, and the
    references that were skipped.

    references must be ordered by project_key(reference); within each
    project, earlier references take a DOI first.
    """
    changes, skips = [], []
    for _, project_references in groupby(references, key=project_key):
        project_references = list(project_references)
        taken = {r.doi.lower() for r in project_references if r.doi}
        for reference in project_references:
            if reference.doi:
                continue
            dois = {doi.lower(): doi for doi in find_dois(reference.description)}
            if not dois:
                continue
            if len(dois) > 1:
                skips.append(Skip(reference, 'the citation includes more than one DOI'))
                continue
            doi = next(iter(dois.values()))
            try:
                validate_doi(doi)
            except ValidationError:
                skips.append(Skip(reference, f'{doi} is not a valid DOI'))
                continue
            if doi.lower() in taken:
                skips.append(Skip(reference, f'another reference in the project has the DOI {doi}'))
                continue
            taken.add(doi.lower())
            changes.append(Change(reference, doi))
    return changes, skips


class Command(BaseCommand):
    help = 'Fill in the DOI of references whose citation already includes one.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Save the changes. Without this option, the changes are only listed.')

    def handle(self, *args, **options):
        apply = options['apply']

        active = Reference.objects.prefetch_related('project').order_by(
            'content_type_id', 'object_id', 'order', 'id')
        published = PublishedReference.objects.select_related('project').order_by(
            'project_id', 'order', 'id')

        active_changes, active_skips = find_backfill(
            active, lambda r: (r.content_type_id, r.object_id))
        published_changes, published_skips = find_backfill(
            published, lambda r: r.project_id)
        changes = active_changes + published_changes
        skips = active_skips + published_skips

        for change in changes:
            self.stdout.write(
                f'{project_label(change.reference)}: reference {change.reference.id}: {change.doi}')
        for skip in skips:
            self.stdout.write(
                f'{project_label(skip.reference)}: reference {skip.reference.id}: '
                f'skipped, because {skip.reason}')

        if apply:
            # Update the rows directly, so that this does not count as a
            # change to the project's content (which would, for example,
            # reset authors' approval of a submission).
            with transaction.atomic():
                for change in changes:
                    type(change.reference).objects.filter(
                        id=change.reference.id, doi='').update(doi=change.doi)
                    # A published reference's link is stored, so give it
                    # the DOI link if it has none
                    if isinstance(change.reference, PublishedReference):
                        PublishedReference.objects.filter(
                            id=change.reference.id, url__isnull=True,
                        ).update(url=f'https://doi.org/{change.doi}')
            summary = f'Filled in {count(len(changes), "DOI")}.'
        else:
            summary = (f'Would fill in {count(len(changes), "DOI")}. '
                       'Run with --apply to save the changes.')
        self.stdout.write(self.style.SUCCESS(f'{summary} Skipped {count(len(skips), "reference")}.'))
