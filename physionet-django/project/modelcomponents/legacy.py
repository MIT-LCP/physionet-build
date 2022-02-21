from datetime import datetime
import os

from django.db import models
from django.utils import timezone
import pytz

from project.modelcomponents.access import License
from project.modelcomponents.coreproject import CoreProject, ProjectType
from project.modelcomponents.fields import SafeHTMLField
from project.modelcomponents.metadata import PublishedPublication, Contact
from project.modelcomponents.publishedproject import PublishedProject


class LegacyProject(models.Model):
    """
    Temporary model for migrating legacy databases
    """
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=100)
    abstract = SafeHTMLField(blank=True, default='')
    full_description = SafeHTMLField()
    doi = models.CharField(max_length=100, blank=True, default='')
    version = models.CharField(max_length=20, default='1.0.0')

    resource_type = models.PositiveSmallIntegerField(default=0)
    publish_date = models.DateField()

    # In case we want a citation
    citation = models.CharField(blank=True, default='', max_length=1000)
    citation_url = models.URLField(blank=True, default='')

    contact_name = models.CharField(max_length=120, default='PhysioNet Support')
    contact_affiliations = models.CharField(max_length=150, default='MIT')
    contact_email = models.EmailField(max_length=255, default='webmaster@physionet.org')

    class Meta:
        default_permissions = ()

    # Put the references as part of the full description

    def __str__(self):
        return ' --- '.join([self.slug, self.title])

    def publish(self, make_file_roots=False):
        """
        Turn into a published project
        """
        p = PublishedProject.objects.create(title=self.title,
            doi=self.doi, slug=self.slug,
            resource_type=ProjectType.objects.get(id=self.resource_type),
            core_project=CoreProject.objects.create(),
            abstract=self.abstract,
            is_legacy=True, full_description=self.full_description,
            version=self.version,
            license=License.objects.get(name='Open Data Commons Attribution License v1.0')
        )

        # Have to set publish_datetime here due to auto_now_add of object
        dt = datetime.combine(self.publish_date, datetime.min.time())
        dt = pytz.timezone(timezone.get_default_timezone_name()).localize(dt)
        p.publish_datetime = dt
        p.save()

        # Related objects
        if self.citation:
            PublishedPublication.objects.create(citation=self.citation,
                url=self.citation_url, project=p)

        Contact.objects.create(name=self.contact_name,
            affiliations=self.contact_affiliations, email=self.contact_email,
            project=p)

        if make_file_roots:
            os.mkdir(p.project_file_root())
            os.mkdir(p.file_root())
