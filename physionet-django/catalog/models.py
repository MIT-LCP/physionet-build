from __future__ import unicode_literals
from django.db import models
# from users.models import User
from ckeditor.fields import RichTextField

# Generic keywords for tagging projects and pages
class Keyword(models.Model):
    word = models.CharField(max_length=50, unique=True)
    # Not sure if we need this actually. 
    slug = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.word

# A published paper
class Paper():
    title = models.CharField(max_length=100, unique=True)



class License(models.Model):
    name = models.CharField(max_length=50, unique=True)
    content = models.TextField()


# Generic contributor
class Contributor():
    name = models.CharField(max_length=100)
    institution = models.CharField(max_length=100)


class HandField(models.Field):

    description = "A hand of cards (bridge style)"

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 104
        super(HandField, self).__init__(*args, **kwargs)


# Generic contact person
class Contact():
    name = models.CharField(max_length=100)
    email = models.EmailField()
    institution = models.CharField(max_length=100)


# Inherited by all - pnw projects, pb databases, ptoolkits, plibraries
class BaseProject(models.Model):

    # The full name of the project
    name = models.CharField(max_length=100, unique=True)
    # The url or directory slug
    slug = models.SlugField(max_length=50, unique=True)
    # The date the database was released into Physiobank. auto_now_add should not equal to True. 
    publishdate = models.DateField()


    # The license for the content. # Will use this when filled in: default=License.objects.get(name='GPL3')
    license = models.ForeignKey(License, default=None, related_name="%(app_label)s_%(class)s",)
    
    # Any keywords tagged by the user
    keywords = models.ManyToManyField(Keyword, related_name="%(app_label)s_%(class)s", blank=True)

    # An overview description. To be shown in index lists and news, not the page itself.
    overview = models.CharField(max_length=1500)

    contributors = Contact()


    # contact = <figure this out>
    # references = <figure this out>

    class Meta:
        abstract = True


# Inherited by published content - databases, toolkits, and documentation
class BasePublishedProject(models.Model):

    DOI = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=50)

    # Who can access the main page and the files. 0 = protected, 1 = open.
    accesspolicy = models.SmallIntegerField(default=1)
    # Users who have access to the project for protected projects
    #members = models.ManyToManyField(User, related_name="%(app_label)s_%(class)s")
    # The data usage agreement
    DUA = RichTextField(default=None)
    
    # The pnw project this published project came from
    originproject = models.ForeignKey('physionetworks.Project', related_name="%(app_label)s_%(class)s", blank=True)


    class Meta:
        abstract = True



