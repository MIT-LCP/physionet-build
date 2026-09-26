from django.conf import settings
from django.db import models
from django.utils import timezone

from project.fields import SafeHTMLField

from challenge.enums import (
    ChallengePhase,
    DatasetType,
    MetricSort,
    SubmissionStatus,
)


class ChallengeConfiguration(models.Model):
    """
    Stores challenge competition settings during the project submission
    phase. Linked to an ActiveProject. When published, this data is
    copied to Challenge + SubmissionSpec.
    """
    active_project = models.OneToOneField(
        'project.ActiveProject',
        on_delete=models.CASCADE,
        related_name='challenge_config',
    )

    # Schedule
    registration_open_datetime = models.DateTimeField(null=True, blank=True)
    start_datetime = models.DateTimeField(null=True, blank=True)
    official_start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)

    # Submission limits
    max_submissions_per_day = models.PositiveIntegerField(default=5)
    max_total_submissions = models.PositiveIntegerField(default=100)
    teams_enabled = models.BooleanField(default=False)

    # Submission spec
    base_image = models.CharField(max_length=200, default='python:3.11-slim')
    entrypoint_command = models.CharField(max_length=500, default='python main.py')
    max_runtime_seconds = models.PositiveIntegerField(default=3600)
    max_memory_mb = models.PositiveIntegerField(default=4096)
    gpu_enabled = models.BooleanField(default=False)
    gpu_type = models.CharField(max_length=50, blank=True, default='')
    cpu_count = models.PositiveIntegerField(default=2)
    input_format = models.JSONField(default=dict, blank=True)
    output_format = models.JSONField(default=dict, blank=True)
    primary_metric_name = models.CharField(max_length=100, default='score')
    primary_metric_sort = models.CharField(
        max_length=4,
        choices=MetricSort.choices,
        default=MetricSort.DESC,
    )
    additional_metrics = models.JSONField(default=list, blank=True)

    # Display
    organizer_name = models.CharField(max_length=200, blank=True, default='')

    # Private evaluation data (uploaded directly to GCS)
    validation_data_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
        help_text='GCS URI for the private validation data.',
    )
    test_data_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
        help_text='GCS URI for the private final test data.',
    )
    evaluation_script_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
        help_text='GCS URI for the evaluation/scoring script.',
    )

    def __str__(self):
        return f'ChallengeConfiguration for {self.active_project}'


class Challenge(models.Model):
    """
    Core challenge configuration, linked one-to-one with a
    PublishedProject of resource_type 2 (Challenge).
    """
    published_project = models.OneToOneField(
        'project.PublishedProject',
        on_delete=models.CASCADE,
        related_name='challenge',
        limit_choices_to={'resource_type': 2},
    )
    slug = models.SlugField(max_length=100, unique=True)
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organized_challenges',
    )
    registration_open_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text='When participants can start registering.',
    )
    start_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text='When the unofficial phase opens for submissions.',
    )
    official_start_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text='When the official phase begins.',
    )
    end_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text='When the challenge closes for submissions.',
    )
    phase = models.CharField(
        max_length=20,
        choices=ChallengePhase.choices,
        default=ChallengePhase.REGISTRATION,
    )
    training_dataset = models.ForeignKey(
        'project.PublishedProject',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='challenge_training_for',
        help_text='Public training dataset for participants.',
    )
    validation_data_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
        help_text='GCS path for the private validation data.',
    )
    test_data_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
        help_text='GCS path for the private final test data.',
    )
    rules = SafeHTMLField(max_length=50000, blank=True, default='')
    evaluation_description = SafeHTMLField(
        max_length=10000, blank=True, default='',
    )
    prizes = SafeHTMLField(max_length=10000, blank=True, default='')
    max_submissions_per_day = models.PositiveIntegerField(default=5)
    max_total_submissions = models.PositiveIntegerField(default=100)
    teams_enabled = models.BooleanField(default=False)
    organizer_name = models.CharField(max_length=200, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_datetime = models.DateTimeField(auto_now_add=True)
    modified_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [
            ('manage_challenge', 'Can manage challenge configuration'),
        ]

    def __str__(self):
        return self.slug

    @property
    def is_registration_open(self):
        now = timezone.now()
        if self.registration_open_datetime and now < self.registration_open_datetime:
            return False
        return self.phase in (ChallengePhase.REGISTRATION, ChallengePhase.UNOFFICIAL)

    @property
    def is_accepting_submissions(self):
        return self.phase == ChallengePhase.UNOFFICIAL and self.is_active


class SubmissionSpec(models.Model):
    """
    Defines the API contract for participant code: base image,
    entrypoint, resource limits, and evaluation configuration.
    """
    challenge = models.OneToOneField(
        Challenge,
        on_delete=models.CASCADE,
        related_name='submission_spec',
    )
    base_image = models.CharField(
        max_length=200, default='python:3.11-slim',
    )
    entrypoint_command = models.CharField(
        max_length=500, default='python main.py',
    )
    max_runtime_seconds = models.PositiveIntegerField(default=3600)
    max_memory_mb = models.PositiveIntegerField(default=4096)
    gpu_enabled = models.BooleanField(default=False)
    gpu_type = models.CharField(max_length=50, blank=True, default='')
    cpu_count = models.PositiveIntegerField(default=2)
    input_format = models.JSONField(
        default=dict, blank=True,
        help_text='JSON describing the expected input structure.',
    )
    output_format = models.JSONField(
        default=dict, blank=True,
        help_text='JSON describing the expected output structure.',
    )
    evaluation_script_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
        help_text='GCS path to the scoring script.',
    )
    primary_metric_name = models.CharField(max_length=100, default='score')
    primary_metric_sort = models.CharField(
        max_length=4,
        choices=MetricSort.choices,
        default=MetricSort.DESC,
    )
    additional_metrics = models.JSONField(
        default=list, blank=True,
        help_text='List of {name, sort} objects for secondary metrics.',
    )

    def __str__(self):
        return f'SubmissionSpec for {self.challenge}'


class Team(models.Model):
    """A team competing in a challenge."""
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='teams',
    )
    name = models.CharField(max_length=100)
    created_datetime = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('challenge', 'name')

    def __str__(self):
        return f'{self.name} ({self.challenge})'


class ChallengeParticipant(models.Model):
    """User registered for a challenge."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='challenge_participations',
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    registered_datetime = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='members',
    )
    is_team_captain = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'challenge')

    def __str__(self):
        return f'{self.user} in {self.challenge}'


class TeamInvitation(models.Model):
    """Invitation to join a team (follows events.CohostInvitation pattern)."""
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='invitations',
    )
    email = models.EmailField(max_length=255)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='challenge_team_invitations_sent',
    )
    request_datetime = models.DateTimeField(auto_now_add=True)
    response_datetime = models.DateTimeField(null=True, blank=True)
    response = models.BooleanField(null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f'Invitation to {self.email} for {self.team}'


class Submission(models.Model):
    """A code submission by a participant or team."""
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='challenge_submissions',
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='submissions',
    )
    code_archive_gcs_uri = models.CharField(max_length=500)
    code_archive_sha256 = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.PENDING,
    )
    cloud_run_job_name = models.CharField(max_length=200, blank=True, default='')
    cloud_run_execution_name = models.CharField(
        max_length=200, blank=True, default='',
    )
    error_message = models.TextField(blank=True, default='')
    container_log_gcs_uri = models.CharField(
        max_length=500, blank=True, default='',
    )
    created_datetime = models.DateTimeField(auto_now_add=True)
    started_datetime = models.DateTimeField(null=True, blank=True)
    completed_datetime = models.DateTimeField(null=True, blank=True)
    description = models.CharField(max_length=500, blank=True, default='')
    is_selected = models.BooleanField(
        default=False,
        help_text='Marks the active submission for the leaderboard.',
    )

    class Meta:
        ordering = ['-created_datetime']

    def __str__(self):
        return f'Submission {self.pk} by {self.submitted_by} ({self.status})'


class Score(models.Model):
    """Individual metric result from a scored submission."""
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='scores',
    )
    metric_name = models.CharField(max_length=100)
    value = models.FloatField()
    dataset = models.CharField(
        max_length=5,
        choices=DatasetType.choices,
    )

    class Meta:
        unique_together = ('submission', 'metric_name', 'dataset')

    def __str__(self):
        return f'{self.metric_name}={self.value} ({self.dataset})'


class LeaderboardEntry(models.Model):
    """Denormalized leaderboard row, pre-computed for fast queries."""
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='leaderboard_entries',
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='leaderboard_entries',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='challenge_leaderboard_entries',
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='leaderboard_entries',
    )
    dataset = models.CharField(
        max_length=5,
        choices=DatasetType.choices,
    )
    primary_score = models.FloatField()
    all_scores = models.JSONField(default=dict, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    updated_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('challenge', 'team', 'user', 'dataset')

    def __str__(self):
        name = self.team or self.user
        return f'#{self.rank} {name} ({self.dataset})'
