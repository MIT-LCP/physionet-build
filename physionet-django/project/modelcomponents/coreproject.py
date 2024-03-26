import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from project.modelcomponents.activeproject import ActiveProject
from project.modelcomponents.publishedproject import PublishedProject


class CoreProject(models.Model):
    """
    The core underlying object that links all versions of the project in
    its various states
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    # doi pointing to the latest version of the published project
    doi = models.CharField(max_length=50, blank=True, null=True)
    # Maximum allowed storage capacity in bytes.
    # Default = 100Mb. Max = 10Tb
    storage_allowance = models.BigIntegerField(default=104857600,
        validators=[MaxValueValidator(109951162777600),
                    MinValueValidator(104857600)])

    class Meta:
        default_permissions = ()

    def active_new_version(self):
        "Whether there is a new version being worked on"
        return bool(self.activeprojects.filter())

    def get_published_versions(self):
        """
        Return a queryset of PublishedProjects, sorted by version.
        """
        return self.publishedprojects.filter().order_by('version_order')

    @property
    def total_published_size(self):
        """
        Total storage size of the published projects.

        This is the sum of the PublishedProjects'
        incremental_storage_size values (which will be less than the
        sum of the main_storage_size values if there are files that
        are shared between versions) and reflects the actual size of
        the data on disk.
        """
        result = self.publishedprojects \
                     .aggregate(total=models.Sum('incremental_storage_size'))
        # The sum will be None if there are no publishedprojects.  It will
        # also be None if any projects have incremental_storage_size=None.
        return result['total'] or 0


class ProjectType(models.Model):
    """
    The project types available on the platform
    """
    id = models.PositiveSmallIntegerField(primary_key=True)
    name = models.CharField(max_length=20)
    description = models.TextField()

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.name


class ProgrammingLanguage(models.Model):
    """
    Language to tag all projects
    """
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.name


def exists_project_slug(slug):
    """
    Whether the slug has been taken by an existing project of any
    kind.
    """
    return bool(ActiveProject.objects.filter(slug=slug) or PublishedProject.objects.filter(slug=slug))
