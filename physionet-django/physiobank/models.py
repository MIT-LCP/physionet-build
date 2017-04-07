from __future__ import unicode_literals
from django.db import models
from catalog.models import BaseProject, BasePublishedProject, Keyword
from physionetworks.models import Project

# A Physiobank database
class Database(BaseProject, BasePublishedProject):
    # Any keywords tagged by the user
    keywords = models.ManyToManyField(Keyword, related_name='database', blank=True)
    # The project from which this item originated (if any)
    originproject = models.ForeignKey(Project, related_name='database', blank=True)


    datatypes = models.ManyToManyField('DataType', related_name='database')
    # All the signal types contained in this database
    signaltypes = models.ManyToManyField('SignalType',related_name='database', blank=True)


    




# Type of data. ie: clinical, waveform, image. For entire database.
class DataType(models.Model):
    name = models.CharField(max_length=50, unique=True)

# Waveform signal types. ie: ecg, eeg, abp.
class SignalType(models.Model):
    name = models.CharField(max_length=50, unique=True)

# Waveform signals. For individual records or their channels.
class Signal(models.Model):
    # Store the name and the signal type it belongs to
    name = models.CharField(max_length=50, unique=True)
    signaltype = models.ForeignKey(SignalType, related_name='signal')

# Waveform annotation types. To add...






