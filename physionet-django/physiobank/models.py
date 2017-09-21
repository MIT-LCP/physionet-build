from __future__ import unicode_literals
from django.db import models
from catalog.models import BaseProject, BasePublishedProject, ProjectDatabase

# A Physiobank database
class Database(BaseProject, BasePublishedProject, ProjectDatabase):
    # Total file size in bytes
    size = models.IntegerField()
    # All the signal classes contained in this database. Redundant, but useful for search.
    signalclasses = models.ManyToManyField('SignalClass',related_name='database', blank=True, default=None)
    # All the clinical data types contained in this database
    clinicaltypes = models.ManyToManyField('ClinicalType',related_name='database', blank=True, default=None)


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
class SignalClass(models.Model):
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.name+' ('+self.description+')'


class AnnotationClass(models.Model):
    """
    Annotation file class categories.
    The ANNOTATORS file in every database must have: extension, description, human_reviewed columns.

    """
    extension = models.CharField(max_length=20)
    description = models.CharField(max_length=50, unique=True)
    human_reviewed = models.BooleanField()
    #standard_wfdb = models.BooleanField()


    def __str__(self):
        return self.extension+' ('+self.description+')'

class AnnotationLabel(models.Model):
    #storevalue = models.SmallIntegerField()
    #symbol = models.CharField(max_length=5)
    #short_description = models.CharField(max_length=15)

    description = models.CharField(max_length=60)

    def __str__(self):
        return self.symbol+' ('+self.description+')'


# Information about WFDB records. Used for database search and wfdb record search.
class Record(models.Model):
    name = models.CharField(max_length=80)
    basefs = models.FloatField(blank=True)
    sig_duration = models.IntegerField(blank=True)  # In seconds
    database = models.ForeignKey('Database', related_name='record', on_delete=models.CASCADE)

    # Other Metadata
    gender = models.BinaryField(blank=True, null=True)
    age = models.SmallIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name+' from database '+self.database.name

# Information about individual single-channel waveform signals. ie: name='II', signaltype = ECG
class Signal(models.Model):
    record = models.ForeignKey('Record', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    sig_class = models.ForeignKey('SignalClass', related_name='signal', on_delete=models.CASCADE)
    fs = models.FloatField()

    def __str__(self):
        return self.name+' from record '+self.record.__str__()

class Annotation(models.Model):
    record = models.ForeignKey('Record', on_delete=models.CASCADE)
    ann_class = models.ForeignKey('AnnotationClass', related_name='annotation')
    labels = models.ManyToManyField('AnnotationLabel', related_name='annotation')

    def __str__(self):
        return self.name+' from record '+self.record.__str__()
