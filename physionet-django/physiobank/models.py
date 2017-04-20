from __future__ import unicode_literals
from django.db import models
from catalog.models import BaseProject, BasePublishedProject, ProjectDatabase

# A Physiobank database
class Database(BaseProject, BasePublishedProject, ProjectDatabase):
    
    # All the signal types contained in this database
    signaltypes = models.ManyToManyField('SignalType',related_name='database', blank=True, default=None)
    # All the signal types contained in this database
    clinicaldatatypes = models.ManyToManyField('ClinicalDataType',related_name='database', blank=True, default=None)

# Type of data. clinical, waveform, image, or other. For entire database.
class DataType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=1000)
    def __str__(self):
        return self.name

# Type of clinical data. EHR, admin, claims, registers, health survey, clinical trial. For databases with clinical data.
class ClinicalDataType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.name
# Waveform signal categories. ie: ecg, eeg, abp. For databases with waveforms.
class SignalType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.name
# Individual waveform signals. For individual records or their channels.
class Signal(models.Model):
    # Store the name and the signal type it belongs to
    name = models.CharField(max_length=50, unique=True)
    signaltype = models.ForeignKey(SignalType, related_name='signal')
    def __str__(self):
        return self.name
# Waveform annotation types. To add...






