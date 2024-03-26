import os

from django.conf import settings
from django.db import models

from project.modelcomponents.metadata import Metadata
from project.modelcomponents.unpublishedproject import UnpublishedProject
from project.modelcomponents.submission import SubmissionInfo


class ArchivedProject(Metadata, UnpublishedProject, SubmissionInfo):
    """
    THIS MODEL WILL BE DEPRECATED. INSTEAD, USE ACTIVEPROJECT
    WITH SUBMISSIONSTATUS=ARCHIVED.

    An archived project. Created when (maps to archive_reason):
    1. A user chooses to 'delete' their ActiveProject.
    2. An ActiveProject is not submitted for too long.
    3. An ActiveProject is submitted and rejected.
    4. An ActiveProject is submitted and times out.
    """
    archive_datetime = models.DateTimeField(auto_now_add=True)
    archive_reason = models.PositiveSmallIntegerField()

    # Subdirectory (under self.files.file_root) where files are stored
    FILE_STORAGE_SUBDIR = 'archived-projects'

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))
