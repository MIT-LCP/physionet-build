from django.db import models
from django.utils.translation import gettext_lazy as _


class ChallengePhase(models.TextChoices):
    SETUP = 'setup', _('Setup')
    ACTIVE = 'active', _('Active')
    REVIEW = 'review', _('Review')
    COMPLETED = 'completed', _('Completed')
    ARCHIVED = 'archived', _('Archived')


class SubmissionStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    BUILDING = 'building', _('Building')
    RUNNING = 'running', _('Running')
    SCORING = 'scoring', _('Scoring')
    COMPLETED = 'completed', _('Completed')
    FAILED = 'failed', _('Failed')
    CANCELLED = 'cancelled', _('Cancelled')
    TIMED_OUT = 'timed_out', _('Timed Out')


class MetricSort(models.TextChoices):
    ASC = 'asc', _('Ascending (lower is better)')
    DESC = 'desc', _('Descending (higher is better)')


class DatasetType(models.TextChoices):
    TRAIN = 'train', _('Training')
    VAL = 'val', _('Validation')
    TEST = 'test', _('Test')
