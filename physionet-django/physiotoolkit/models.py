from __future__ import unicode_literals

from django.db import models
from catalog.models import BaseProject, BasePublishedProject, ProjectToolkit

# Physiotoolkit software package
class Toolkit(BaseProject, BasePublishedProject, ProjectToolkit):
    pass
    


