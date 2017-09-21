from __future__ import unicode_literals

from django.db import models




class Metadata():
    """

    """

    doi = models.CharField(max_length=80, unique=True)





class Creator():
    first_name = models.CharField()




class Project():
    data_cite_info = models.OneToOneField('project.DataCiteInfo', related_name='project')


