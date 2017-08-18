from __future__ import unicode_literals
from django.db import models
from users.models import User
from ckeditor.fields import RichTextField
from uuid import uuid4

# Generic keywords for tagging projects and pages
class Keyword(models.Model):
    word = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.word

# A published paper
class Reference(models.Model):
    title = models.CharField(max_length=100, unique=True)
    url = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.title

class License(models.Model):
    name = models.CharField(max_length=50, unique=True)
    url = models.URLField()
    def __str__(self):
        return self.name

# Generic contributor
class Contributor(models.Model):
    name = models.CharField(max_length=100)
    institution = models.CharField(max_length=100)

    def __str__(self):
        return self.name

# Generic contact person
class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    institution = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Link(models.Model):
    description = models.CharField(max_length=100)
    url = models.CharField(max_length=150)

    def __str__(self):
        return self.url

class DUA(models.Model):
    name = models.CharField(max_length=100)
    content = RichTextField()
    

def user_directory_path(self, filename):
    print 'media/projects/%s/%s' % (self.Pid, filename)
    return 'media/projects/%s/%s' % (self.Pid, filename)

class File(models.Model):
    id   = models.AutoField(primary_key = True, unique = True, editable = False)
    name = models.CharField(max_length = 80)
    directory = models.CharField(max_length = 200)
    file = models.FileField(upload_to = user_directory_path, default = '', blank = True, null = True)
    size = models.BigIntegerField(default=0, blank = True, null = True)
    lastmtime = models.DateField()
    extension = models.CharField(max_length = 10, default = '',blank = True, null = True)

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
    overview = models.TextField(max_length=1500)
    # People who own/contribute the content
    contributors = models.ManyToManyField('catalog.Contributor', related_name="%(app_label)s_%(class)s", blank=True)

    contacts = models.ManyToManyField('catalog.Contact', related_name="%(app_label)s_%(class)s", blank=True)

    # references = models.ManyToManyField('Reference')
    # additional_references
    
    # Links to other pages 
    associated_pages = models.ManyToManyField('catalog.Link', related_name="%(app_label)s_%(class)s", blank=True)
    # Acknowledgements
    acknowledgements = models.TextField(blank=True)

    files = models.ManyToManyField('catalog.File', related_name="%(app_label)s_%(class)s", blank=True)

    def __str__(self):
        return self.name
        
    class Meta:
        abstract = True


# Inherited by published content - databases, toolkits, and documentation
class BasePublishedProject(models.Model):

    DOI = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=50)

    # Open or protected
    isopen = models.BooleanField(default=True)
    # Users who control access to the project for protected projects
    authorizers = models.ManyToManyField(User, related_name="%(app_label)s_%(class)s_authorizer", blank=True)
    # Users who have access to the project for protected projects
    members = models.ManyToManyField(User, related_name="%(app_label)s_%(class)s_member", blank=True)
    # The data usage agreement
    DUA = RichTextField(blank=True, default='')
    
    # The pnw project this published project came from
    originproject = models.ForeignKey('physionetworks.Project', related_name="%(app_label)s_%(class)s", blank=True, null=True)

    # The number of visits
    visits = models.IntegerField(default=0)
    # The volume of downloads
    downloads = models.IntegerField(default=0)
    
    # Changelog
    changelog = RichTextField(blank=True, default='')
    
    class Meta:
        abstract = True


# Extra models for specific project types
class ProjectDatabase(models.Model):
    # A description of the data collection
    collection = RichTextField(default='', blank=True, null=True)
    # Describing the names and layout of files
    filedescription = RichTextField(default='', blank=True, null=True)
    datatypes = models.ManyToManyField('physiobank.DataType', related_name="%(app_label)s_%(class)s")



class ProjectToolkit(models.Model):
    # Programming languages used
    languages = models.ManyToManyField('physiotoolkit.Language', related_name="%(app_label)s_%(class)s")
    # Install instructions
    installation = RichTextField()
    # Usage instructions
    usage = RichTextField(default = '',blank = True, null = True)
    # Platforms tested
    testedplatforms = RichTextField(default = '',blank = True, null = True)


#class ProjectGuide(models.Model):





# ---------- Non-model Classes ---------- #

# For displaying lists of files in project pages
# All attributes are human readable strings
class DisplayFile(object):

    def __init__(self, name, size, lastmtime, description):
        # name is also the (relative) url
        self.name = name
        self.size = size
        self.lastmtime = lastmtime
        self.description = description

class DisplayDirectory(object):

     def __init__(self, name, size, lastmtime, description):
        # name is also the (relative) url
        self.name = name
        self.size = size
        self.lastmtime = lastmtime
        self.description = description   

