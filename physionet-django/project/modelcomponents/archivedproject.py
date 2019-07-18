import os

from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericRelation

from project.modelcomponents.metadata import Metadata
from project.modelcomponents.unpublishedproject import UnpublishedProject
from project.modelcomponents.submission import SubmissionInfo
from project.modelcomponents.section import SectionContent


class ArchivedProject(Metadata, UnpublishedProject, SubmissionInfo):
    """
    An archived project. Created when (maps to archive_reason):
    1. A user chooses to 'delete' their ActiveProject.
    2. An ActiveProject is not submitted for too long.
    3. An ActiveProject is submitted and rejected.
    4. An ActiveProject is submitted and times out.
    """
    archive_datetime = models.DateTimeField(auto_now_add=True)
    archive_reason = models.PositiveSmallIntegerField()
    content = GenericRelation(SectionContent)

    # Where all the archived project files are kept
    FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'archived-projects')

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))
