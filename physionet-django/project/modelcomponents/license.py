from django.db import models

from project.enums import AccessPolicy
from project.fields import SafeHTMLField
from project.validators import validate_version


class License(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    version = models.CharField(max_length=15, default='', validators=[validate_version])
    is_active = models.BooleanField(default=True)
    text_content = models.TextField(default='')
    html_content = SafeHTMLField(default='')
    home_page = models.URLField()
    # A project must choose a license with a matching access policy and
    # compatible resource type
    access_policy = models.PositiveSmallIntegerField(choices=AccessPolicy.choices(), default=AccessPolicy.OPEN)
    # A license can be used for one or more resource types.
    # This is a comma delimited char field containing allowed types.
    # ie. '0' or '0,2' or '1,3,4'
    project_types = models.ManyToManyField('project.ProjectType', related_name='licenses')
    # A protected license has associated DUA content

    class Meta:
        default_permissions = ('add',)
        unique_together = (('name', 'version'),)

    def __str__(self):
        return self.name
