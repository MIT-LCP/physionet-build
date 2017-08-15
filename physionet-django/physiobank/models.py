from __future__ import unicode_literals
from django.db import models
from catalog.models import BaseProject, BasePublishedProject, ProjectDatabase

# A Physiobank database
class Database(BaseProject, BasePublishedProject, ProjectDatabase):
    # Total file size in bytes
    size = models.IntegerField()
    # All the signal types contained in this database. Redundant, but useful for search.
    signaltypes = models.ManyToManyField('SignalType',related_name='database', blank=True, default=None)
    # All the clinical data types contained in this database
    clinicaltypes = models.ManyToManyField('ClinicalType',related_name='database', blank=True, default=None)
    # The wfdb records contained
    #wfdbrecords = models.OneToManyField('WFDB_Record',related_name='database', blank=True, default=None)

# Type of data. clinical, waveform, image, or other. For entire database.
class DataType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=1000)
    def __str__(self):
        return self.name

# Type of clinical data. EHR, admin, claims, registers, health survey, clinical trial. For databases with clinical data.
class ClinicalType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.name

# Waveform signal categories. ie: ecg, eeg, abp. For databases with waveforms. Why not define in wfdb?
class SignalType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.name

# Information about WFDB records. Used for database search and wfdb record search.
class WFDB_Record(models.Model):
    name = models.CharField(max_length=80)
    basefs = models.FloatField(blank=True)
    sigduration = models.IntegerField(blank=True)  # In seconds

    database = models.ForeignKey('Database', related_name='record')

    # Other Metadata
    gender = models.BinaryField(blank=True, null=True)
    age = models.SmallIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name

# Individual waveform signals. For individual records or their channels. ie: name='II', signaltype = ECG
class Signal(models.Model):
    record = models.ForeignKey('WFDB_Record')
    name = models.CharField(max_length=50)
    signaltype = models.ForeignKey(SignalType, related_name='signal')
    # full fs = basefs * sampsperframe
    full_fs = models.FloatField()

    def __str__(self):
        return self.name

# Waveform annotation types. To add...





