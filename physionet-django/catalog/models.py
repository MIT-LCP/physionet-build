from __future__ import unicode_literals
from django.db import models

# Generic keywords for tagging projects and pages
class Keyword(models.Model):
    word = models.CharField(max_length=50, unique=True)
    # Not sure if we need this actually. 
    slug = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.word

# A published paper
class Paper(models.Model):
    title = models.CharField(max_length=100, unique=True)

class License(models.Model):
    name = models.CharField(max_length=50, unique=True)
    content = models.TextField()

# A contact 
class Contact():
    # The person's name
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    institution = models.CharField(max_length=100)

# Inherited by all - pnw projects, pb databases, ptoolkits, plibraries
class BaseProject(models.Model):

    # The full name of the project
    name = models.CharField(max_length=100, unique=True)
    # The url or directory slug
    slug = models.SlugField(max_length=50, unique=True)
    # The date the database was released into Physiobank. auto_now_add should not equal to True. 
    publishdate = models.DateField()


    # This is not here because each model needs its own related_name
    #keywords = models.ManyToManyField(Keyword, related_name='database', blank=True)


    # An overview description. To be shown in index lists and news, not the page itself.
    overview = models.TextField(max_length=1500)

    # contributors = <figure this out>
    # contact = <figure this out>
    # references = <figure this out>

    class Meta:
        abstract = True


# Inherited by published content - databases, toolkits, and documentation
class BasePublishedProject(models.Model):

    DOI = models.CharField(max_length=50, unique=True)
    version = models.CharField(max_length=50)

    # This is not here because each model needs its own related_name. 
    #originproject = models.ForeignKey('physionetworks.Project', related_name='project', blank=True)

    class Meta:
        abstract = True



