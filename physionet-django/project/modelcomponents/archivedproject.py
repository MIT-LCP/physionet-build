import os

from django.conf import settings
from django.db import models

from project.modelcomponents.metadata import Metadata
from project.modelcomponents.unpublishedproject import UnpublishedProject
from project.modelcomponents.submission import SubmissionInfo


class ArchivedProjectTraining(models.Model):
    archivedproject = models.ForeignKey('project.ArchivedProject', on_delete=models.CASCADE)
    trainingtype = models.ForeignKey('user.TrainingType', on_delete=models.CASCADE)
    temporary = models.BooleanField(default=False, null=True)


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
    required_trainings = models.ManyToManyField('user.TrainingType',
                                                through='project.ArchivedProjectTraining', related_name='%(class)s')

    # Where all the archived project files are kept
    FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'archived-projects')

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))
