from __future__ import unicode_literals

from django.db import models
from catalog.models import BaseProject, BasePublishedProject, ProjectToolkit

# Physiotoolkit software package
class Toolkit(BaseProject, BasePublishedProject, ProjectToolkit):
    pass
    


# Programming language. ie. C, Matlab, Python.
class Language(models.Model):
    name = models.CharField(max_length=50, unique=True)
