from django.db import models
from project.fields import SafeHTMLField
from project.validators import validate_version

from project.enums import AccessPolicy
from project.modelcomponents.anonymousaccess import AnonymousAccess
from project.modelcomponents.dataaccess import DataAccess
from project.modelcomponents.dataaccessrequest import DataAccessRequest
from project.modelcomponents.dataaccessrequestreviewer import DataAccessRequestReviewer
from project.modelcomponents.duasignature import DUASignature
from project.modelcomponents.license import License


class DUA(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    version = models.CharField(max_length=15, default='', validators=[validate_version])
    is_active = models.BooleanField(default=True)
    html_content = SafeHTMLField(default='')
    access_template = SafeHTMLField(default='')
    access_policy = models.PositiveSmallIntegerField(choices=AccessPolicy.choices(), default=AccessPolicy.OPEN)
    project_types = models.ManyToManyField('project.ProjectType', related_name='duas')

    class Meta:
        default_permissions = ('add',)
        unique_together = (('name', 'version'),)

    def __str__(self):
        return self.name
