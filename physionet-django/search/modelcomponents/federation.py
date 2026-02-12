"""
Models for federated search across multiple PhysioNet instances.

This module implements a REST API Pull-Based Synchronization architecture
where PhysioNet instances can share project metadata to enable unified
cross-site search functionality.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta


class FederatedSite(models.Model):
    """
    Registry of federated PhysioNet instances.

    Each PhysioNet deployment can register other instances to enable
    federated search. Sites periodically sync metadata from registered peers.

    Example sites:
        - physionet.org (MIT)
        - healthdatanexus.ca (UofT)
    """

    # Sync status choices
    STATUS_NEVER = 'never'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_IN_PROGRESS = 'in_progress'

    SYNC_STATUS_CHOICES = [
        (STATUS_NEVER, 'Never synced'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_IN_PROGRESS, 'In progress'),
    ]

    # Basic site information
    site_identifier = models.SlugField(
        max_length=50,
        unique=True,
        help_text='Unique identifier for this site (e.g., "physionet-mit")'
    )
    site_name = models.CharField(
        max_length=200,
        help_text='Display name for this site (e.g., "PhysioNet")'
    )
    api_base_url = models.URLField(
        max_length=500,
        help_text='Base URL for the federation API'
    )

    # Site status
    is_active = models.BooleanField(
        default=True,
        help_text='Whether to sync data from this site'
    )

    # Synchronization tracking
    last_sync_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of last successful sync'
    )
    last_sync_status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default=STATUS_NEVER,
        help_text='Status of most recent sync attempt'
    )

    # Metadata
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['site_name']
        verbose_name = 'Federated Site'
        verbose_name_plural = 'Federated Sites'
        indexes = [
            models.Index(fields=['is_active', 'last_sync_datetime']),
        ]

    def __str__(self):
        return f"{self.site_name} ({self.site_identifier})"

    def needs_sync(self):
        """
        Check if this site needs to be synced based on the configured frequency.

        Returns:
            bool: True if sync is needed, False otherwise
        """
        if not self.is_active:
            return False

        if not self.last_sync_datetime:
            return True

        sync_frequency = timedelta(
            hours=getattr(settings, 'FEDERATION_SYNC_FREQUENCY_HOURS', 24)
        )

        return timezone.now() - self.last_sync_datetime >= sync_frequency

    def mark_sync_started(self):
        """Mark sync as in progress."""
        self.last_sync_status = self.STATUS_IN_PROGRESS
        self.save(update_fields=['last_sync_status'])

    def mark_sync_success(self):
        """Mark sync as successful."""
        self.last_sync_datetime = timezone.now()
        self.last_sync_status = self.STATUS_SUCCESS
        self.save(update_fields=['last_sync_datetime', 'last_sync_status'])

    def mark_sync_failed(self):
        """Mark sync as failed."""
        self.last_sync_status = self.STATUS_FAILED
        self.save(update_fields=['last_sync_status'])

    def get_api_endpoint(self):
        """
        Get the full API endpoint URL for federation sync.

        Returns:
            str: Full URL to the standard published projects list endpoint
        """
        # Remove trailing slash if present
        base_url = self.api_base_url.rstrip('/')
        return f"{base_url}/api/v1/project/published/"

    def get_detail_endpoint(self, slug, version):
        """
        Get the full API endpoint URL for a specific project detail.

        Args:
            slug: Project slug
            version: Project version

        Returns:
            str: Full URL to the project detail endpoint
        """
        base_url = self.api_base_url.rstrip('/')
        return f"{base_url}/api/v1/project/published/{slug}/{version}/"


class FederatedProject(models.Model):
    """
    Cached metadata from remote PhysioNet instances.

    This model stores a lightweight copy of project metadata from federated
    sites to enable local search without network latency. The actual project
    files remain on the source site.
    """

    # Source tracking
    source_site = models.ForeignKey(
        FederatedSite,
        on_delete=models.CASCADE,
        related_name='cached_projects',
        help_text='The federated site this project belongs to'
    )

    # Persistent identifier - UUID from the source site
    public_project_uuid = models.UUIDField(
        db_index=True,
        help_text='UUID of the project from the source site'
    )

    # Core project metadata (mirrors PublishedProject fields)
    slug = models.SlugField(
        max_length=50,
        db_index=True,
        help_text='Project slug on the source site'
    )
    version = models.CharField(
        max_length=15,
        help_text='Project version'
    )
    title = models.CharField(
        max_length=200,
        help_text='Project title'
    )
    abstract = models.TextField(
        help_text='Project abstract'
    )
    doi = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Digital Object Identifier'
    )

    # Remote reference
    source_url = models.URLField(
        max_length=500,
        help_text='URL to project page on source site'
    )

    # Classification metadata (stored as strings from API)
    resource_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Resource type (e.g., "Database", "Software")'
    )
    access_policy = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Access policy (e.g., "Open", "Restricted")'
    )

    # Dates and storage
    publish_datetime = models.DateTimeField(
        help_text='When the project was published on source site'
    )
    main_storage_size = models.BigIntegerField(
        default=0,
        help_text='Storage size in bytes'
    )

    # Topics (stored as JSON array for simplicity)
    topics = models.JSONField(
        default=list,
        null=True,
        blank=True,
        help_text='List of topic tags (e.g., ["ehr", "critical care"])'
    )

    # Sync tracking
    last_fetched = models.DateTimeField(
        auto_now=True,
        help_text='Last time this project metadata was updated'
    )

    class Meta:
        unique_together = [['source_site', 'public_project_uuid']]
        verbose_name = 'Federated Project'
        verbose_name_plural = 'Federated Projects'
        ordering = ['-publish_datetime', 'title']
        indexes = [
            models.Index(fields=['public_project_uuid']),
            models.Index(fields=['slug', 'version']),
            models.Index(fields=['publish_datetime']),
            models.Index(fields=['resource_type']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return f"{self.title} v{self.version} (from {self.source_site.site_name})"


class FederationSyncLog(models.Model):
    """
    Audit trail of synchronization operations.

    Tracks each sync attempt with statistics and error messages for
    monitoring and debugging.
    """

    # Sync status choices
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'

    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PARTIAL, 'Partial success'),
    ]

    # Which site was synced
    site = models.ForeignKey(
        FederatedSite,
        on_delete=models.CASCADE,
        related_name='sync_logs',
        help_text='The site that was synced'
    )

    # Timing
    started_at = models.DateTimeField(
        help_text='When sync started'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When sync completed'
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        help_text='Overall status of this sync'
    )

    # Statistics
    projects_fetched = models.IntegerField(
        default=0,
        help_text='Total projects fetched from API'
    )
    projects_created = models.IntegerField(
        default=0,
        help_text='New projects added to cache'
    )
    projects_updated = models.IntegerField(
        default=0,
        help_text='Existing projects updated'
    )
    projects_deleted = models.IntegerField(
        default=0,
        help_text='Projects removed during full refresh'
    )

    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text='Error message if sync failed'
    )

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Federation Sync Log'
        verbose_name_plural = 'Federation Sync Logs'
        indexes = [
            models.Index(fields=['site', '-started_at']),
            models.Index(fields=['status', '-started_at']),
        ]

    def __str__(self):
        duration = ''
        if self.completed_at:
            delta = self.completed_at - self.started_at
            duration = f" ({delta.total_seconds():.1f}s)"  # noqa: E231
        return f"{self.site.site_name} - {self.status} @ {self.started_at}{duration}"

    def get_duration_seconds(self):
        """Get sync duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
