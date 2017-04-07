from __future__ import unicode_literals

from django.db import models
from sharing.models import BaseProject, BasePublishedProject


# Physiotoolkit software package
class Toolkit(BaseProject, BasePublishedProject):
    languages = models.ManyToManyField(Language, related_name='toolkit')

# Programming language. ie. C, Matlab, Python.
class Language(models.Model):
    name = models.CharField(max_length=50, unique=True)
