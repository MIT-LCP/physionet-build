from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from project.modelcomponents.generic import BaseInvitation
from user.validators import validate_affiliation


class AuthorInvitation(BaseInvitation):
    """
    Invitation to join a project as an author
    """
    # The target email
    email = models.EmailField(max_length=255)
    # User who made the invitation
    inviter = models.ForeignKey('user.User', on_delete=models.CASCADE)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return 'ActiveProject: {0} To: {1} By: {2}'.format(self.project, self.email,
                                                     self.inviter)

    @staticmethod
    def get_user_invitations(user, exclude_duplicates=True):
        """
        Get all active author invitations to a user
        """
        emails = user.get_emails()
        invitations = AuthorInvitation.objects.filter(email__in=emails,
            is_active=True).order_by('-request_datetime')

        # Remove duplicate invitations to the same project
        if exclude_duplicates:
            project_slugs = []
            remove_ids = []
            for invitation in invitations:
                if invitation.project.id in project_slugs:
                    remove_ids.append(invitation.id)
                else:
                    project_slugs.append(invitation.project.id)
            invitations = invitations.exclude(id__in=remove_ids)

        return invitations


class Affiliation(models.Model):
    """
    Affiliations belonging to an author
    """
    MAX_LENGTH = 202
    MAX_AFFILIATIONS = 3
    name = models.CharField(max_length=MAX_LENGTH,
                            validators=[validate_affiliation])
    author = models.ForeignKey('project.Author', related_name='affiliations',
        on_delete=models.CASCADE)

    class Meta:
        default_permissions = ()
        unique_together = (('name', 'author'),)


class PublishedAffiliation(models.Model):
    """
    Affiliations belonging to a published author
    """
    name = models.CharField(max_length=202, validators=[validate_affiliation])
    author = models.ForeignKey('project.PublishedAuthor',
        related_name='affiliations', on_delete=models.CASCADE)

    class Meta:
        default_permissions = ()
        unique_together = (('name', 'author'),)


class BaseAuthor(models.Model):
    """
    Base model for a project's author/creator. Credited for creating the
    resource.

    Datacite definition: "The main researchers involved in producing the
    data, or the authors of the publication, in priority order."
    """
    user = models.ForeignKey('user.User', related_name='%(class)ss',
        on_delete=models.CASCADE)
    display_order = models.PositiveSmallIntegerField()
    is_submitting = models.BooleanField(default=False)
    is_corresponding = models.BooleanField(default=False)
    # When they approved the project for publication
    approval_datetime = models.DateTimeField(null=True)

    class Meta:
        abstract = True

    def __str__(self):
        # Best representation for form display
        user = self.user
        return '{} --- {}'.format(user.username, user.email)


class Author(BaseAuthor):
    """
    The author model for ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')
    corresponding_email = models.ForeignKey('user.AssociatedEmail', null=True,
        on_delete=models.SET_NULL)
    creation_date = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ()
        unique_together = (('user', 'content_type', 'object_id',),
                           ('display_order', 'content_type', 'object_id'))

    def get_full_name(self, reverse=False):
        """
        The name is tied to the profile. There is no form for authors
        to change their names. Return the full name.
        Args:
            reverse: Format of the return string. If False (default) then
                'firstnames lastname'. If True then 'lastname, firstnames'.
        """
        last = self.user.profile.last_name
        first = self.user.profile.first_names
        if reverse:
            return ', '.join([last, first])
        else:
            return ' '.join([first, last])

    def initialed_name(self, commas=True, periods=True):
        """
        Return author's name in citation style.
        """
        last = self.user.profile.last_name
        first = self.user.profile.first_names
        final_string = '{}, {}'.format(
            last, ' '.join('{}.'.format(i[0]) for i in first.split()))

        if not commas:
            final_string = final_string.replace(',', '')
        if not periods:
            final_string = final_string.replace('.', '')

        return final_string

    def disp_name_email(self):
        """
        """
        return '{} ({})'.format(self.get_full_name(), self.user.email)

    def import_profile_info(self):
        """
        Import profile information (names) into the Author object.
        Also create affiliation object if present in profile.
        """
        profile = self.user.profile
        if profile.affiliation:
            Affiliation.objects.create(name=profile.affiliation,
                                       author=self)
            return True
        return False

    def set_display_info(self, set_affiliations=True):
        """
        Set the fields used to display the author
        """
        user = self.user
        self.name = user.profile.get_full_name()
        self.email = user.email
        self.username = user.username

        if set_affiliations:
            self.text_affiliations = [a.name for a in self.affiliations.all()]


class PublishedAuthor(BaseAuthor):
    """
    The author model for PublishedProject
    """
    first_names = models.CharField(max_length=100, default='')
    last_name = models.CharField(max_length=50, default='')
    corresponding_email = models.EmailField(null=True)
    project = models.ForeignKey('project.PublishedProject',
        related_name='authors', db_index=True, on_delete=models.CASCADE)

    class Meta:
        default_permissions = ()
        unique_together = (('user', 'project'),
                           ('display_order', 'project'))

    def get_full_name(self, reverse=False):
        """
        Return the full name.
        Args:
            reverse: Format of the return string. If False (default) then
                'firstnames lastname'. If True then 'lastname, firstnames'.
        """
        if reverse:
            return ', '.join([self.last_name, self.first_names])
        else:
            return ' '.join([self.first_names, self.last_name])

    def set_display_info(self):
        """
        Set the fields used to display the author
        """
        self.name = self.get_full_name()
        self.username = self.user.username
        self.email = self.user.email
        self.text_affiliations = [a.name for a in self.affiliations.all()]

    def initialed_name(self, commas=True, periods=True):

        final_string = '{}, {}'.format(self.last_name, ' '.join('{}.'
                                       .format(i[0]) for i in self.first_names
                                       .split()))

        if not commas:
            final_string = final_string.replace(',', '')
        if not periods:
            final_string = final_string.replace('.', '')

        return final_string
