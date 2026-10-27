import logging

import requests
from background_task import background
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from console.tasks import associated_task
import project.models as models
from project import openalex

LOGGER = logging.getLogger(__name__)


@associated_task('project.ActiveProject', 'project_id')
@background()
def prepare_active_project_files(project_id):
    """
    Prepare files in an active project for publication.

    This task is meant to be invoked after completing copyediting and
    before the project is published (i.e., it is expected to run while
    the project is in the NEEDS_APPROVAL and/or NEEDS_PUBLICATION
    states.)

    This function should be the final step performed on the project
    files before publication.  It includes:

    - making every file read-only

    - generating a checksum file (SHA256SUMS.txt)

    - calculating the total size of the files (main_storage_size)
    """
    project = models.ActiveProject.objects.get(id=project_id)
    modified_datetime = project.modified_datetime

    # Do nothing if checksums are already up-to-date.
    if project.checksums_valid_datetime == modified_datetime:
        return

    # Fix file permissions: make all files read-only, clear
    # set-uid/set-gid/sticky modes, make scripts executable
    # (r-xr-xr-x), and make non-scripts non-executable (r--r--r--).
    project.files.chmod_tree_files_readonly(project.file_root())

    # Generate the checksum file.
    project.make_checksum_file()

    # Calculate the main_storage_size (including the checksum file.)
    main_storage_size = project.files.published_project_storage_used(project)

    # Only save the main_storage_size and checksums_valid_datetime if
    # the project has not been modified since we started.
    project.refresh_from_db()
    if project.modified_datetime == modified_datetime:
        project.main_storage_size = main_storage_size
        project.checksums_valid_datetime = modified_datetime
        project.save(update_fields=[
            'main_storage_size',
            'checksums_valid_datetime',
        ])


@associated_task('project.PublishedProject', 'project_id')
@background()
def finalize_published_project_files(project_id):
    """
    Make the directories of a published project read-only.
    """
    project = models.PublishedProject.objects.get(id=project_id)
    project.files.chmod_tree_subdirs_readonly(project.file_root())


@associated_task('project.PublishedProject', 'project_id')
@background()
def create_published_project_zip(project_id):
    """
    Generate a ZIP archive of a published project.
    """
    project = models.PublishedProject.objects.get(id=project_id)
    project.make_zip()


@background()
def refresh_scholar_data(doi):
    """
    Fetch dataset statistics for a DOI from the ScholarData API and
    store them.

    On failure the previously stored data is kept, and the error is
    logged rather than raised so that the task is not retried; the next
    refresh is queued after ScholarData.REFRESH_INTERVAL.

    Does nothing if ENABLE_SCHOLAR_DATA_API has been turned off since
    the task was queued.
    """
    if not settings.ENABLE_SCHOLAR_DATA_API:
        return

    url = f'{settings.SCHOLAR_DATA_API_URL}/datasets/by-doi'
    try:
        response = requests.get(url, params={'doi': doi}, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        LOGGER.warning('Unable to fetch ScholarData for %s: %r', doi, e)
        return

    models.ScholarData.objects.filter(doi=doi).update(data=data)


def citing_work_dois(core_project):
    """
    Return the DOIs to look up when finding works that cite a project,
    as a pair (dataset_dois, publication_dois).

    The dataset DOIs are the project's own DOIs (one per version, plus
    the DOI for the latest version). The publication DOIs are taken from
    the URLs of the primary publications of every version.
    """
    versions = core_project.publishedprojects.all()
    dataset_dois = {
        doi.lower() for doi in [core_project.doi, *versions.values_list('doi', flat=True)] if doi
    }
    publication_dois = set()
    for url in models.PublishedPublication.objects.filter(
            project__core_project=core_project).values_list('url', flat=True):
        doi = openalex.extract_doi(url)
        if doi:
            publication_dois.add(doi)
    return dataset_dois, publication_dois - dataset_dois


@background()
def refresh_citing_works(core_project_id):
    """
    Fetch the works citing a project from OpenAlex and store them,
    replacing the previously stored list.

    On failure the previously stored list is kept, and the error is
    logged rather than raised so that the task is not retried; the next
    refresh is queued after CitingWorksRefresh.REFRESH_INTERVAL.

    Does nothing if ENABLE_OPENALEX_API has been turned off since the
    task was queued.
    """
    if not settings.ENABLE_OPENALEX_API:
        return

    core_project = models.CoreProject.objects.filter(id=core_project_id).first()
    if core_project is None:
        return

    dataset_dois, publication_dois = citing_work_dois(core_project)
    try:
        works = openalex.fetch_citing_works(dataset_dois, publication_dois)
    except Exception as e:
        LOGGER.warning('Unable to fetch citing works for core project %s: %r', core_project_id, e)
        return

    with transaction.atomic():
        models.CitingWork.objects.filter(core_project=core_project).delete()
        models.CitingWork.objects.bulk_create(
            [models.CitingWork(core_project=core_project, **fields) for fields in works.values()],
            batch_size=1000,
        )
        models.CitingWorksRefresh.objects.filter(core_project=core_project).update(
            fetch_datetime=timezone.now())
