from __future__ import unicode_literals

from django.db import models
from catalog.models import BaseProject, BasePublishedProject, Keyword
from physionetworks.models import Project

# Physiotoolkit software package
class Toolkit(BaseProject, BasePublishedProject):
    
    # Programming languages used
    languages = models.ManyToManyField('Language', related_name='toolkit')

    

# Programming language. ie. C, Matlab, Python.
class Language(models.Model):
    name = models.CharField(max_length=50, unique=True)
