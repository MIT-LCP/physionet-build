from __future__ import unicode_literals
from django.db import models
from users.models import User
from ckeditor.fields import RichTextField

# Generic keywords for tagging projects and pages
class Keyword(models.Model):
    word = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.word

# A published paper
class Reference(models.Model):
    title = models.CharField(max_length=100, unique=True)
    link = models.CharField(max_length=100, unique=True)


class License(models.Model):
    name = models.CharField(max_length=50, unique=True)
    content = models.TextField()
    def __str__(self):
        return self.name

# Generic contributor
class Contributor(models.Model):
    name = models.CharField(max_length=100)
    institution = models.CharField(max_length=100)

# Generic contact person
class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    institution = models.CharField(max_length=100)

class Link(models.Model):
    description = models.CharField(max_length=100)
    url = models.CharField(max_length=150)


# Inherited by all - pnw projects, pb databases, ptoolkits, plibraries
class BaseProject(models.Model):

    # The full name of the project
    name = models.CharField(max_length=100, unique=True)
    # The url or directory slug
    slug = models.SlugField(max_length=50, unique=True)
    # The date the project was published
    publishdate = models.DateField(blank=True)

    # The license for the content. # Will use this when filled in: default=License.objects.get(name='GPL3')
    license = models.ForeignKey('catalog.License', default=None, related_name="%(app_label)s_%(class)s",)
    
    # Any keywords tagged by the user
    keywords = models.ManyToManyField('catalog.Keyword', related_name="%(app_label)s_%(class)s", blank=True)

    # An overview description. To be shown in index lists and news, not the page itself.
    overview = models.CharField(max_length=1500)
    # People who own/contribute the content
    contributors = models.ManyToManyField('catalog.Contributor', related_name="%(app_label)s_%(class)s", blank=True)

    contacts = models.ManyToManyField('catalog.Contact', related_name="%(app_label)s_%(class)s", blank=True)

    # references = models.ManyToManyField('Reference')
    # additional_references
    
    # Links to other pages 
    associated_pages = models.ManyToManyField('catalog.Link', related_name="%(app_label)s_%(class)s", blank=True)
    # Acknowledgements
    acknowledgements = models.TextField(blank=True)


    #files = models.ManyToManyField('catalog.File', related_name="%(app_label)s_%(class)s")

    def __str__(self):
        return self.name
        
    class Meta:
        abstract = True



# Inherited by published content - databases, toolkits, and documentation
class BasePublishedProject(models.Model):

    DOI = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=50)

    # Who can access the main page and the files. 0 = protected, 1 = open.
    accesspolicy = models.SmallIntegerField(default=1)
    # Users who control access to the project for protected projects
    authorizers = models.ManyToManyField(User, related_name="%(app_label)s_%(class)s_authorizer")
    # Users who have access to the project for protected projects
    members = models.ManyToManyField(User, related_name="%(app_label)s_%(class)s_member")
    # The data usage agreement
    DUA = RichTextField(default=None)
    
    # The pnw project this published project came from
    originproject = models.ForeignKey('physionetworks.Project', related_name="%(app_label)s_%(class)s", blank=True)

    # The number of visits
    visits = models.IntegerField(default=0)
    # The volume of downloads
    downloads = models.IntegerField(default=0)

    class Meta:
        abstract = True


# Extra models for specific project types
class ProjectDatabase(models.Model):
    # A description of the data collection
    collection = models.TextField()
    # Describing the names and layout of files
    filedescription = models.TextField()
    datatypes = models.ManyToManyField('physiobank.DataType', related_name="%(app_label)s_%(class)s")


class ProjectToolkit(models.Model):
    # Programming languages used
    languages = models.ManyToManyField('physiotoolkit.Language', related_name="%(app_label)s_%(class)s")
    # Usage instructions
    usage = models.TextField()
    # Platforms tested
    testedplatforms = models.TextField()


#class ProjectGuide(models.Model):
