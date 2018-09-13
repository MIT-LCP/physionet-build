import os
import pdb

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .validators import UsernameValidator

import logging

logger = logging.getLogger(__name__)

class Affiliation(models.Model):
    """
    Profile affiliation

    """
    order = models.SmallIntegerField(default=0)
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=100, default='')
    city = models.CharField(max_length=50)
    country = models.CharField(max_length=100)

    profile = models.ForeignKey('user.Profile', related_name='affiliations')


class UserManager(BaseUserManager):
    """
    Manager object with methods to create
    User instances.
    """
    def create_user(self, email, password, username, is_active=False,
                    is_admin=False, first_name='', middle_names='',
                    last_name=''):
        if is_admin:
            is_active = True

        user = self.model(email=self.normalize_email(email.lower()),
                          username=self.model.normalize_username(username.lower()),
                          is_active=is_active, is_admin=is_admin)
        user.set_password(password)
        user.save(using=self._db)

        profile = Profile.objects.create(user=user, first_name=first_name,
                                         middle_names=middle_names,
                                         last_name=last_name)
        return user

    def create_superuser(self, email, password, username):
        user = self.create_user(email=email, password=password,
                                username=username, is_admin=True)
        return user

    def get_by_natural_key(self, email):
        return self.get(email=email)


class User(AbstractBaseUser):
    """
    The user authentication model
    """

    email = models.EmailField(max_length=255, unique=True)
    username = models.CharField(max_length=150, unique=True,
        help_text='Required. 150 characters or fewer. Letters, digits and - only.',
        validators=[UsernameValidator()],
        error_messages={
            'unique': "A user with that username already exists."})
    join_date = models.DateField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    # Mandatory fields for the default authentication backend
    is_active = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    USERNAME_FIELD = 'username'
    EMAIL_FIELD = 'email'

    REQUIRED_FIELDS = ['email']

    def natural_key(self):
        return (self.email,)

    def validate_unique(self, exclude=None):
        """
        Add additional check to the non-primary AssociatedEmail objects.
        The email field in User should be in sync with primary AssociatedEmails.
        """
        super(User, self).validate_unique(exclude=exclude)

        if AssociatedEmail.objects.filter(email=self.email.lower(), is_primary_email=False):
            raise ValidationError({'email':'User with this email already exists.'})
        if User.objects.filter(email=self.email.lower()):
            raise ValidationError({'email':'User with this email already exists.'})
        if User.objects.filter(username=self.username.lower()):
            raise ValidationError({'username':'User with this username already exists.'})

    # Mandatory methods for default authentication backend
    def get_full_name(self):
        return self.profile.get_full_name()

    def get_short_name(self):
        return self.profile.first_name

    def __str__(self):
        return '{} - {}'.format(self.username, self.email)

    objects = UserManager()

    # Mandatory attributes for using the admin panel
    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        return True

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        return self.is_admin

    # Custom fields and methods
    def get_emails(self):
        "Get list of all email strings"
        return [ae.email for ae in self.associated_emails.all()]

    def get_names(self):
        return self.profile.get_names()


class AssociatedEmail(models.Model):
    """
    An email the user associates with their account
    """
    user = models.ForeignKey('user.User', related_name='associated_emails')
    email = models.EmailField(max_length=255, unique=True)
    is_primary_email = models.BooleanField(default=False)
    added_date = models.DateTimeField(auto_now_add=True, null=True)
    verification_date = models.DateTimeField(null=True)
    is_verified = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)

    def __str__(self):
        return self.email


@receiver(post_save, sender=User)
def create_associated_email(sender, **kwargs):
    """
    Creates and attaches a primary AssociatedEmail when a User object is
    created.
    """
    user = kwargs['instance']
    if kwargs['created']:
        email = AssociatedEmail(user=user, email=user.email, is_primary_email=True)
        if user.is_active:
            email.verification_date = timezone.now()
            email.is_verified = True
        email.save()


@receiver(post_save, sender=User)
def update_associated_emails(sender, **kwargs):
    """
    Updates the primary/non-primary status of AssociatedEmails when the
    User object's email field is updated.
    """
    user = kwargs['instance']
    if not kwargs['created'] and kwargs['update_fields'] and 'email' in kwargs['update_fields']:
        old_primary_email = AssociatedEmail.objects.get(user=user, is_primary_email=True)
        new_primary_email = AssociatedEmail.objects.get(user=user, email=user.email)
        old_primary_email.is_primary_email = False
        new_primary_email.is_primary_email = True
        old_primary_email.save()
        new_primary_email.save()


def photo_path(instance, filename):
    """
    Storage path of profile photo. Keep the original file extension only.
    """
    return 'user/{0}/{1}'.format(instance.user.id, '.'.join(['profile-photo', filename.split('.')[-1]]))

class Profile(models.Model):
    """
    Class storing profile information which is
    not directly related to account activity
    or authentication.

    This model should contain some fields which help map
    projects to datacite:
    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.0.pdf
    """
    user = models.OneToOneField('user.User', related_name='profile')

    first_name = models.CharField(max_length=30)
    middle_names = models.CharField(max_length=100, blank=True, default='')
    last_name = models.CharField(max_length=30)
    affiliation = models.CharField(max_length=60, blank=True, default='')
    location = models.CharField(max_length=60, blank=True, default='')
    website = models.URLField(default='', blank=True, null=True)
    photo = models.ImageField(upload_to=photo_path, blank=True, null=True)
    is_credentialed = models.BooleanField(default=False)
    credential_datetime = models.DateTimeField(blank=True, null=True)

    MAX_PHOTO_SIZE = 2 * 1024 ** 2

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        if self.middle_names:
            return ' '.join([self.first_name, self.middle_names,
                           self.last_name])
        else:
            return ' '.join([self.first_name, self.last_name])

    def get_names(self):
        return self.first_name, self.middle_names, self.last_name

    def delete_photo(self):
        """
        Delete the photo
        """
        if self.photo:
            os.remove(self.photo.path)
            self.photo = None
            self.save()


class DualAuthModelBackend():
    """
    This is a ModelBacked that allows authentication with either a username or an email address.

    """
    def authenticate(self, username=None, password=None):
        if '@' in username:
            kwargs = {'email': username.lower()}
        else:
            kwargs = {'username': username.lower()}
        try:
            user = get_user_model().objects.get(**kwargs)
            if user.check_password(password):
                logger.info('User logged in {0}'.format(user.email))
                return user
        except User.DoesNotExist:
            logger.error('Unsuccessful authentication {0}'.format(username.lower()))
            return None

    def get_user(self, username):
        try:
            return get_user_model().objects.get(pk=username)
        except get_user_model().DoesNotExist:
            return None
