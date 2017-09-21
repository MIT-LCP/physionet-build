from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from django.conf import settings
from operator import itemgetter
from django.db import models
from uuid import uuid4
import os
# from __future__ import unicode_literals

CONTIGUOUS_STATES = (('N/A','       '), ('AL', 'Alabama'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming'))
NON_CONTIGUOUS_STATES = (('AK', 'Alaska'), ('HI', 'Hawaii'))
US_TERRITORIES = (('AS', 'American Samoa'), ('GU', 'Guam'), ('MP', 'Northern Mariana Islands'), ('PR', 'Puerto Rico'), ('VI', 'Virgin Islands'))
USA = sorted(CONTIGUOUS_STATES + NON_CONTIGUOUS_STATES + US_TERRITORIES, key=itemgetter(1))

# We have to alter the UserManager class in order to make it use email for authentication.
# Both functions have to be created, create_user (mere mortal) and create_superuser (god like person).
class UserManager(BaseUserManager):
    def create_user(self, email, password, **kwargs):
        user = self.model(email=self.normalize_email(email), is_admin=False, is_superuser=False, is_active=False, **kwargs)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **kwargs):
        user = self.model( email=self.normalize_email(email), is_admin=True, is_superuser=True, is_active=True, **kwargs )
        user.set_password(password)
        user.save(using=self._db)
        return user

def user_directory_path(instance, filename):
    location = 'Users/%s/%s.%s' % (instance.email, "Profile", filename.split('.')[-1])    
    return location

# Function to overwrite of the picture if already exists
class OverwriteStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        # If the filename already exists, remove it as if it was a true file system
        if self.exists(name):
            os.remove(os.path.join(settings.MEDIA_ROOT, name))
        return name

# Definition of the user
# This is a custom class becuase the default user doesnt allow email authentication.
# So we removed the username and added all the things for physionet.
class User(AbstractBaseUser, PermissionsMixin):
    USERNAME_FIELD = 'email'
    id = models.AutoField(primary_key=True, unique=True, editable=False,)
    email = models.EmailField(verbose_name='email address',max_length=255,unique=True,)
    is_active = models.BooleanField(default=False,)
    is_admin = models.BooleanField(default=False,)
    first_name = models.CharField(max_length = 100, default='',)
    last_name = models.CharField(max_length = 100, default='',)
    organization = models.CharField(max_length=50,  default='',)
    department = models.CharField(max_length=50, default='',)
    city = models.CharField(max_length=50, default='',)
    state = models.CharField(max_length=40, default='',blank=True, null=True, choices=USA)   
    country = models.CharField(max_length=50, default='',)
    url = models.URLField(default='', blank=True, null=True)
    photo = models.ImageField(upload_to=user_directory_path, storage=OverwriteStorage(), default='', blank=True, null=True)

    objects = UserManager()

    def get_full_name(self):
        # The user is identified by their email address
        return self.first_name + " " + self.last_name

    def get_short_name(self):
        # The user is identified by their email address
        return self.email

    def __str__(self): 
        return self.email

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

# Class to define a action made by a user that require a unique link with a expiration time
# Actions could be Activation or password reset
# A UUID will be automaticly generated with the current time and the users email
class user_action(models.Model):
    code   = models.UUIDField(unique=True, default=uuid4, editable=False)
    date   = models.DateTimeField(editable=False, default=timezone.now)
    email  = models.EmailField(verbose_name='email address',max_length=255, default='',blank=False, null=False)
    action = models.CharField(max_length=15, default='',)



