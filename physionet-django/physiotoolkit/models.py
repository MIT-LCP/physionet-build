from __future__ import unicode_literals

from django.db import models
from catalog.models import BaseProject, BasePublishedProject, Keyword
from physionetworks.models import Project

# Physiotoolkit software package
class Toolkit(BaseProject, BasePublishedProject):
    
    # Any keywords tagged by the user
    keywords = models.ManyToManyField(Keyword, related_name='toolkit', blank=True)
    # The project from which this item originated (if any)
    originproject = models.ForeignKey(Project, related_name='toolkit', blank=True)

    # Programming languages used
    languages = models.ManyToManyField('Language', related_name='toolkit')

    

# Programming language. ie. C, Matlab, Python.
class Language(models.Model):
    name = models.CharField(max_length=50, unique=True)
