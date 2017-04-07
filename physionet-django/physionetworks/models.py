from __future__ import unicode_literals

from django.db import models
from catalog.models import BaseProject, License, Keyword
# from users.models import User
from ckeditor.fields import RichTextField


# Physionetworks project
class Project(BaseProject):

    # Any keywords tagged by the user
    keywords = models.ManyToManyField(Keyword, related_name='project', blank=True)

    #owner  = models.ForeignKey(User, related_name='project', blank=True)
    #collaborators = models.ManyToManyField(User, related_name='project', blank=True)
    #reviewers = models.ManyToManyField(User, related_name='project', blank=True)
    # Who can access/download the files. 0 = reviewer/collaborator, 1 = everyone
    accesspolicy = models.SmallIntegerField(default=0)
    # Who can see the project listed. 0 = reviewer/collaborator, 1 = everyone
    viewpolicy = models.SmallIntegerField(default=1)
    # Whether users can apply to be reviewer/collaborator. 0 = no, 1 = yes.
    applicationpolicy = models.SmallIntegerField(default=1)
    # 0, 1, 2 = database, toolkit, documentation
    projecttype = models.SmallIntegerField()
    # The license for the content
    license = models.ForeignKey(License)
    # Storage allowance in MB
    storage = models.SmallIntegerField(default=1024)



    

    # Full description
    description = RichTextField()



