from background_task import background

from console.tasks import associated_task
import project.models as models


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
