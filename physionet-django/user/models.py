import logging
import os
import pdb
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
# from django.contrib.auth. import user_logged_in
from django.contrib.auth import get_user_model, signals
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import EmailValidator, FileExtensionValidator, integer_validator, validate_integer
from django.db import DatabaseError, models, transaction
from django.db.models import CharField
from django.db.models.functions import Lower
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.translation import ugettext as _

from project.models import AccessPolicy
from user import validators
from user.userfiles import UserFiles

logger = logging.getLogger(__name__)

# Support the LOWER() keyword in querysets (e.g. 'Q(email__lower__in)')
CharField.register_lookup(Lower, "lower")

COUNTRIES = (
    ("AF", _("Afghanistan")),
    ("AX", _("Åland Islands")),
    ("AL", _("Albania")),
    ("DZ", _("Algeria")),
    ("AS", _("American Samoa")),
    ("AD", _("Andorra")),
    ("AO", _("Angola")),
    ("AI", _("Anguilla")),
    ("AQ", _("Antarctica")),
    ("AG", _("Antigua and Barbuda")),
    ("AR", _("Argentina")),
    ("AM", _("Armenia")),
    ("AW", _("Aruba")),
    ("AU", _("Australia")),
    ("AT", _("Austria")),
    ("AZ", _("Azerbaijan")),
    ("BS", _("Bahamas")),
    ("BH", _("Bahrain")),
    ("BD", _("Bangladesh")),
    ("BB", _("Barbados")),
    ("BY", _("Belarus")),
    ("BE", _("Belgium")),
    ("BZ", _("Belize")),
    ("BJ", _("Benin")),
    ("BM", _("Bermuda")),
    ("BT", _("Bhutan")),
    ("BO", _("Bolivia (Plurinational State of)")),
    ("BQ", _("Bonaire, Sint Eustatius and Saba")),
    ("BA", _("Bosnia and Herzegovina")),
    ("BW", _("Botswana")),
    ("BV", _("Bouvet Island")),
    ("BR", _("Brazil")),
    ("IO", _("British Indian Ocean Territory")),
    ("BN", _("Brunei Darussalam")),
    ("BG", _("Bulgaria")),
    ("BF", _("Burkina Faso")),
    ("BI", _("Burundi")),
    ("CV", _("Cabo Verde")),
    ("KH", _("Cambodia")),
    ("CM", _("Cameroon")),
    ("CA", _("Canada")),
    ("KY", _("Cayman Islands")),
    ("CF", _("Central African Republic")),
    ("TD", _("Chad")),
    ("CL", _("Chile")),
    ("CN", _("China")),
    ("CX", _("Christmas Island")),
    ("CC", _("Cocos (Keeling) Islands")),
    ("CO", _("Colombia")),
    ("KM", _("Comoros")),
    ("CD", _("Congo (the Democratic Republic of the)")),
    ("CG", _("Congo")),
    ("CK", _("Cook Islands")),
    ("CR", _("Costa Rica")),
    ("CI", _("Côte d'Ivoire")),
    ("HR", _("Croatia")),
    ("CU", _("Cuba")),
    ("CW", _("Curaçao")),
    ("CY", _("Cyprus")),
    ("CZ", _("Czechia")),
    ("DK", _("Denmark")),
    ("DJ", _("Djibouti")),
    ("DM", _("Dominica")),
    ("DO", _("Dominican Republic")),
    ("EC", _("Ecuador")),
    ("EG", _("Egypt")),
    ("SV", _("El Salvador")),
    ("GQ", _("Equatorial Guinea")),
    ("ER", _("Eritrea")),
    ("EE", _("Estonia")),
    ("SZ", _("Eswatini")),
    ("ET", _("Ethiopia")),
    ("FK", _("Falkland Islands  [Malvinas]")),
    ("FO", _("Faroe Islands")),
    ("FJ", _("Fiji")),
    ("FI", _("Finland")),
    ("FR", _("France")),
    ("GF", _("French Guiana")),
    ("PF", _("French Polynesia")),
    ("TF", _("French Southern Territories")),
    ("GA", _("Gabon")),
    ("GM", _("Gambia")),
    ("GE", _("Georgia")),
    ("DE", _("Germany")),
    ("GH", _("Ghana")),
    ("GI", _("Gibraltar")),
    ("GR", _("Greece")),
    ("GL", _("Greenland")),
    ("GD", _("Grenada")),
    ("GP", _("Guadeloupe")),
    ("GU", _("Guam")),
    ("GT", _("Guatemala")),
    ("GG", _("Guernsey")),
    ("GN", _("Guinea")),
    ("GW", _("Guinea-Bissau")),
    ("GY", _("Guyana")),
    ("HT", _("Haiti")),
    ("HM", _("Heard Island and McDonald Islands")),
    ("VA", _("Holy See")),
    ("HN", _("Honduras")),
    ("HK", _("Hong Kong")),
    ("HU", _("Hungary")),
    ("IS", _("Iceland")),
    ("IN", _("India")),
    ("ID", _("Indonesia")),
    ("IR", _("Iran (Islamic Republic of)")),
    ("IQ", _("Iraq")),
    ("IE", _("Ireland")),
    ("IM", _("Isle of Man")),
    ("IL", _("Israel")),
    ("IT", _("Italy")),
    ("JM", _("Jamaica")),
    ("JP", _("Japan")),
    ("JE", _("Jersey")),
    ("JO", _("Jordan")),
    ("KZ", _("Kazakhstan")),
    ("KE", _("Kenya")),
    ("KI", _("Kiribati")),
    ("KP", _("Korea (the Democratic People's Republic of)")),
    ("KR", _("Korea (the Republic of)")),
    ("KW", _("Kuwait")),
    ("KG", _("Kyrgyzstan")),
    ("LA", _("Lao People's Democratic Republic")),
    ("LV", _("Latvia")),
    ("LB", _("Lebanon")),
    ("LS", _("Lesotho")),
    ("LR", _("Liberia")),
    ("LY", _("Libya")),
    ("LI", _("Liechtenstein")),
    ("LT", _("Lithuania")),
    ("LU", _("Luxembourg")),
    ("MO", _("Macao")),
    ("MK", _("Macedonia (the former Yugoslav Republic of)")),
    ("MG", _("Madagascar")),
    ("MW", _("Malawi")),
    ("MY", _("Malaysia")),
    ("MV", _("Maldives")),
    ("ML", _("Mali")),
    ("MT", _("Malta")),
    ("MH", _("Marshall Islands")),
    ("MQ", _("Martinique")),
    ("MR", _("Mauritania")),
    ("MU", _("Mauritius")),
    ("YT", _("Mayotte")),
    ("MX", _("Mexico")),
    ("FM", _("Micronesia (Federated States of)")),
    ("MD", _("Moldova (the Republic of)")),
    ("MC", _("Monaco")),
    ("MN", _("Mongolia")),
    ("ME", _("Montenegro")),
    ("MS", _("Montserrat")),
    ("MA", _("Morocco")),
    ("MZ", _("Mozambique")),
    ("MM", _("Myanmar")),
    ("NA", _("Namibia")),
    ("NR", _("Nauru")),
    ("NP", _("Nepal")),
    ("NL", _("Netherlands")),
    ("NC", _("New Caledonia")),
    ("NZ", _("New Zealand")),
    ("NI", _("Nicaragua")),
    ("NE", _("Niger")),
    ("NG", _("Nigeria")),
    ("NU", _("Niue")),
    ("NF", _("Norfolk Island")),
    ("MP", _("Northern Mariana Islands")),
    ("NO", _("Norway")),
    ("OM", _("Oman")),
    ("PK", _("Pakistan")),
    ("PW", _("Palau")),
    ("PS", _("Palestine, State of")),
    ("PA", _("Panama")),
    ("PG", _("Papua New Guinea")),
    ("PY", _("Paraguay")),
    ("PE", _("Peru")),
    ("PH", _("Philippines")),
    ("PN", _("Pitcairn")),
    ("PL", _("Poland")),
    ("PT", _("Portugal")),
    ("PR", _("Puerto Rico")),
    ("QA", _("Qatar")),
    ("RE", _("Réunion")),
    ("RO", _("Romania")),
    ("RU", _("Russian Federation")),
    ("RW", _("Rwanda")),
    ("BL", _("Saint Barthélemy")),
    ("SH", _("Saint Helena, Ascension and Tristan da Cunha")),
    ("KN", _("Saint Kitts and Nevis")),
    ("LC", _("Saint Lucia")),
    ("MF", _("Saint Martin (French part)")),
    ("PM", _("Saint Pierre and Miquelon")),
    ("VC", _("Saint Vincent and the Grenadines")),
    ("WS", _("Samoa")),
    ("SM", _("San Marino")),
    ("ST", _("Sao Tome and Principe")),
    ("SA", _("Saudi Arabia")),
    ("SN", _("Senegal")),
    ("RS", _("Serbia")),
    ("SC", _("Seychelles")),
    ("SL", _("Sierra Leone")),
    ("SG", _("Singapore")),
    ("SX", _("Sint Maarten (Dutch part)")),
    ("SK", _("Slovakia")),
    ("SI", _("Slovenia")),
    ("SB", _("Solomon Islands")),
    ("SO", _("Somalia")),
    ("ZA", _("South Africa")),
    ("GS", _("South Georgia and the South Sandwich Islands")),
    ("SS", _("South Sudan")),
    ("ES", _("Spain")),
    ("LK", _("Sri Lanka")),
    ("SD", _("Sudan")),
    ("SR", _("Suriname")),
    ("SJ", _("Svalbard and Jan Mayen")),
    ("SE", _("Sweden")),
    ("CH", _("Switzerland")),
    ("SY", _("Syrian Arab Republic")),
    ("TW", _("Taiwan")),
    ("TJ", _("Tajikistan")),
    ("TZ", _("Tanzania, United Republic of")),
    ("TH", _("Thailand")),
    ("TL", _("Timor-Leste")),
    ("TG", _("Togo")),
    ("TK", _("Tokelau")),
    ("TO", _("Tonga")),
    ("TT", _("Trinidad and Tobago")),
    ("TN", _("Tunisia")),
    ("TR", _("Turkey")),
    ("TM", _("Turkmenistan")),
    ("TC", _("Turks and Caicos Islands")),
    ("TV", _("Tuvalu")),
    ("UG", _("Uganda")),
    ("UA", _("Ukraine")),
    ("AE", _("United Arab Emirates")),
    ("GB", _("United Kingdom of Great Britain and Northern Ireland")),
    ("UM", _("United States Minor Outlying Islands")),
    ("US", _("United States of America")),
    ("UY", _("Uruguay")),
    ("UZ", _("Uzbekistan")),
    ("VU", _("Vanuatu")),
    ("VE", _("Venezuela (Bolivarian Republic of)")),
    ("VN", _("Viet Nam")),
    ("VG", _("Virgin Islands (British)")),
    ("VI", _("Virgin Islands (U.S.)")),
    ("WF", _("Wallis and Futuna")),
    ("EH", _("Western Sahara")),
    ("YE", _("Yemen")),
    ("ZM", _("Zambia")),
    ("ZW", _("Zimbabwe")),
)


class UserManager(BaseUserManager):
    """
    Manager object with methods to create
    User instances.
    """
    def create_user(self, email, password, username, is_active=False,
                    is_admin=False, first_names='', last_name=''):
        if is_admin:
            is_active = True

        user = self.model(email=self.normalize_email(email.lower()),
                          username=self.model.normalize_username(username.lower()),
                          is_active=is_active, is_admin=is_admin)
        user.set_password(password)
        user.save(using=self._db)

        profile = Profile.objects.create(user=user, first_names=first_names,
                                         last_name=last_name)
        return user

    def create_superuser(self, email, password, username):
        user = self.create_user(email=email, password=password,
                                username=username, is_admin=True)
        return user


def validate_unique_email(email):
    """
    Add additional check to the non-primary AssociatedEmail objects.
    The email field in User should be in sync with primary AssociatedEmails.
    """
    if AssociatedEmail.objects.filter(email=email.lower(), is_primary_email=False):
        raise ValidationError(_("User with this email already exists."),
            code='email_not_unique',)
    if User.objects.filter(email=email.lower()):
        raise ValidationError(_("User with this email already exists."),
            code='email_not_unique',)


class User(AbstractBaseUser):
    """
    The user authentication model
    """
    email = models.EmailField(max_length=255, unique=True,
        validators=[validate_unique_email, EmailValidator()])
    username = models.CharField(max_length=50, unique=True,
        help_text='Required. 4 to 50 characters. Letters, digits and - only. Must start with a letter.',
        validators=[validators.UsernameValidator()],
        error_messages={
            'unique': "A user with that username already exists."})
    join_date = models.DateField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    # Mandatory fields for the default authentication backend
    is_active = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    is_credentialed = models.BooleanField(default=False)
    credential_datetime = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = 'username'
    EMAIL_FIELD = 'email'

    REQUIRED_FIELDS = ['email']
    # Where all the users' files are kept
    RELATIVE_FILE_ROOT = 'users'
    FILE_ROOT = os.path.join(UserFiles().file_root, RELATIVE_FILE_ROOT)

    def is_superuser(self):
        return (self.is_admin,)

    # Mandatory methods for default authentication backend
    def get_full_name(self):
        return self.profile.get_full_name()

    def get_short_name(self):
        return self.profile.first_names

    def __str__(self):
        return self.username

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
    def get_emails(self, is_verified=True, include_primary=True):
        """
        Get list of email address strings.

        Args:
            is_verified (bool): If True, return verified email addresses only.
            include_primary (bool): If True, include the primary email address
                in the list.
        """
        if include_primary:
            emails = self.associated_emails.filter(is_verified=is_verified)
        else:
            emails = self.associated_emails.filter(is_verified=is_verified,
                                                   is_primary_email=False)
        return [ae.email for ae in emails]

    def get_primary_email(self):
        """
        Get the primary associated email
        """
        return self.associated_emails.get(is_primary_email=True)

    def get_names(self):
        return self.profile.get_names()

    def disp_name_email(self):
        return '{} --- {}'.format(self.get_full_name(), self.email)

    def file_root(self, relative=False):
        "Where the user's files are stored"
        if relative:
            return os.path.join(User.RELATIVE_FILE_ROOT, self.username)
        return os.path.join(User.FILE_ROOT, self.username)


class UserLogin(models.Model):
    """Represent users' logins, one per record"""
    user = models.ForeignKey('user.User', related_name='login_time',
        on_delete=models.CASCADE)
    login_date = models.DateTimeField(auto_now_add=True, null=True)
    ip = models.CharField(max_length=50,  blank=True, default='', null=True)

def update_user_login(sender, **kwargs):
    user = kwargs.pop('user', None)
    request = kwargs.pop('request', None)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = ''
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    UserLogin.objects.create(user=user, ip=ip)
    logger.info('User logged in {0}'.format(user.email))

signals.user_logged_in.connect(update_user_login, sender=User)


class AssociatedEmail(models.Model):
    """
    An email the user associates with their account
    """
    user = models.ForeignKey('user.User', related_name='associated_emails',
        on_delete=models.CASCADE)
    email = models.EmailField(max_length=255, unique=True,
        validators=[validate_unique_email, EmailValidator()])
    is_primary_email = models.BooleanField(default=False)
    added_date = models.DateTimeField(auto_now_add=True, null=True)
    verification_date = models.DateTimeField(null=True)

    # Secret token sent to the user, which they must supply to prove
    # they control the email address
    verification_token = models.CharField(max_length=32, blank=True, null=True)

    is_verified = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)

    # Time limit for verification: maximum number of days after
    # 'added_date' during which 'verification_token' may be used.
    VERIFICATION_TIMEOUT_DAYS = 7

    def __str__(self):
        return self.email

    def check_token(self, token):
        """
        Check whether the supplied verification token is valid.
        """
        if not token or not self.verification_token:
            return False
        if not constant_time_compare(token, self.verification_token):
            return False
        if self.is_verified:
            return False
        age = timezone.now() - self.added_date
        if age >= timedelta(days=AssociatedEmail.VERIFICATION_TIMEOUT_DAYS):
            return False
        return True

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
    Storage path of profile photo relative to media root.
    Keep the original file extension only.
    """
    return 'users/{0}/{1}'.format(instance.user.username, '.'.join(['profile-photo', filename.split('.')[-1]]))

def training_report_path(instance, filename):
    """
    Storage path of CITI training report
    """
    return 'credential-applications/{}/{}'.format(instance.slug, 'training-report.pdf')


class LegacyCredential(models.Model):
    """
    Stores instances of profiles that were credentialed on the old
    pn website.
    """
    first_names = models.CharField(max_length=100, blank=True, default='')
    last_name = models.CharField(max_length=100, blank=True, default='')
    email = models.EmailField(max_length=255, unique=True)
    country = models.CharField(max_length=100, blank=True, default='')
    # These dates are stored as strings in the legacy system.
    # All are credentialed for mimic
    mimic_approval_date = models.CharField(max_length=100)
    eicu_approval_date = models.CharField(max_length=100, blank=True,
        default='')
    # Their stated reason for using the data
    info = models.CharField(max_length=300, blank=True, default='')
    # Whether the credentialing has been migrated to an account on the
    # new site
    migrated = models.BooleanField(default=False)
    migration_date = models.DateTimeField(null=True)
    migrated_user = models.ForeignKey('user.User', null=True, on_delete=models.CASCADE)
    
    reference_email = models.CharField(max_length=255, blank=True, default='')

    revoked_datetime = models.DateTimeField(null=True)

    def __str__(self):
        return self.email

    def is_legacy(self):
        return True

    def revoke(self):
        """
        Revokes a legacy application.
        """
        # Removes credentialing from the user
        with transaction.atomic():
            self.revoked_datetime = timezone.now()

            self.migrated_user.is_credentialed = False
            self.migrated_user.credential_datetime = None

            self.migrated_user.save()
            self.save()

        logger.info('Credentialing for user {0} has been removed.'.format(
            self.migrated_user.email))


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
    user = models.OneToOneField('user.User', related_name='profile',
        on_delete=models.CASCADE)
    first_names = models.CharField(max_length=100, validators=[validators.validate_name])
    last_name = models.CharField(max_length=50, validators=[validators.validate_name])
    affiliation = models.CharField(max_length=250, blank=True, default='',
        validators=[validators.validate_affiliation])
    location = models.CharField(max_length=100, blank=True, default='',
        validators=[validators.validate_location])
    website = models.URLField(default='', blank=True, null=True)
    photo = models.ImageField(upload_to=photo_path, blank=True, null=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg'],
        'Allowed filetypes are png and jpg only.')])

    MAX_PHOTO_SIZE = 2 * 1024 ** 2

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return ' '.join([self.first_names, self.last_name])

    def get_names(self):
        return self.first_names, self.last_name

    def delete_photo(self):
        """
        Delete the photo
        """
        if self.photo:
            UserFiles().remove_photo(UserFiles().get_photo_path(self))
            self.photo = None
            self.save()


class Orcid(models.Model):
    """
    Class for storing ORCID account information.
    Here are examples of expected formats from a sandbox account:
    orcid_id: 0000-0002-8983-9907
    access_token: c4548597-e368-4acb-bd06-1d8bcf13de46
    refresh_token: 3c68e7a9-7418-4d8d-bf31-1afcd2b7c742
    token_expiration: 2242899965.166591
    where the token_expiration is in unix timestamp format (seconds since Jan 1st 1970)
    """
    user = models.OneToOneField('user.User', related_name='orcid',
                                on_delete=models.CASCADE)
    orcid_id = models.CharField(max_length=50, default='', blank=True,
                          validators=[validators.validate_orcid_id])
    name = models.CharField(max_length=50, default='', blank=True)
    access_token = models.CharField(max_length=50, default='', blank=True,
                                    validators=[validators.validate_orcid_token])
    refresh_token = models.CharField(max_length=50, default='', blank=True,
                                     validators=[validators.validate_orcid_token])
    token_type = models.CharField(max_length=50, default='', blank=True)
    token_scope = models.CharField(max_length=50, default='', blank=True)
    token_expiration = models.DecimalField(max_digits=50, decimal_places=40, default=0)

    @staticmethod
    def get_orcid_url():
        return settings.ORCID_DOMAIN

class DualAuthModelBackend():
    """
    This is a ModelBacked that allows authentication with either a username or an email address.

    """
    def authenticate(self, request, username=None, password=None):
        if '@' in username:
            kwargs = {'email': username.lower()}
        else:
            kwargs = {'username': username.lower()}
        try:
            user = get_user_model().objects.get(**kwargs)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            logger.error('Unsuccessful authentication {0}'.format(username.lower()))
            return None

    def get_user(self, user_id):
        try:
            return get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None

class CredentialApplication(models.Model):
    """
    An application to become credentialed
    """
    RESEARCHER_CATEGORIES = (
        (0, 'Student'),
        (7, 'Graduate Student'),
        (1, 'Postdoc'),
        (2, 'Academic Researcher'),
        (3, 'Hospital Researcher'),
        (4, 'Industry Researcher'),
        (5, 'Government Researcher'),
        (6, 'Independent Researcher'),
    )

    REFERENCE_CATEGORIES = (
        (0, 'Supervisor (required for students and Postdocs)'),
        (1, 'Colleague'),
        (2, 'Coauthor'),
        (3, 'Other'),
    )

    COURSE_CATEGORIES = (
        (0, 'Not for a course'),
        (1, 'I am taking a course using the data'),
    )

    REFERENCE_RESPONSES = (
        ('', '-----------'),
        (1, 'No'),
        (2, 'Yes')
    )

    REJECT_ACCEPT_WITHDRAW = (
        ('', '-----------'),
        (1, 'Reject'),
        (2, 'Accept'),
        (3, 'Withdrawn'),
        (4, 'Revoked')
    )

    # Maximum size for training_completion_report
    MAX_REPORT_SIZE = 2 * 1024 * 1024

    # Location for storing files associated with the application
    FILE_ROOT = os.path.join(UserFiles().file_root, 'credential-applications')

    slug = models.SlugField(max_length=20, unique=True, db_index=True)
    application_datetime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey('user.User', related_name='credential_applications',
        on_delete=models.CASCADE)
    # Personal fields
    first_names = models.CharField(max_length=100, validators=[validators.validate_name])
    last_name = models.CharField(max_length=50, validators=[validators.validate_name])
    researcher_category = models.PositiveSmallIntegerField(choices=RESEARCHER_CATEGORIES)
    # Organization fields
    organization_name = models.CharField(max_length=200,
        validators=[validators.validate_organization])
    job_title = models.CharField(max_length=60,
        validators=[validators.validate_job_title])
    city = models.CharField(max_length=100,
        validators=[validators.validate_city])
    state_province = models.CharField(max_length=100,
        validators=[validators.validate_state], default='', blank=True)
    country = models.CharField(max_length=2, choices=COUNTRIES)
    webpage = models.URLField(default='', blank=True)
    zip_code = models.CharField(max_length=60,
        validators=[validators.validate_zipcode])
    suffix = models.CharField(max_length=60,
        validators=[validators.validate_suffix], default='', blank=True)
    # Human resources training
    training_course_name = models.CharField(max_length=100, default='',
        blank=True, validators=[validators.validate_training_course])
    training_completion_date = models.DateField(null=True, blank=True)
    training_completion_report = models.FileField(
        upload_to=training_report_path, validators=[FileExtensionValidator(
            ['pdf'], 'File must be a pdf.')])
    training_completion_report_url = models.URLField(blank=True, null=True)
    # Course info
    course_category = models.PositiveSmallIntegerField(choices=COURSE_CATEGORIES,
        null=True, blank=True)
    course_info = models.CharField(max_length=100, default='', blank=True,
        validators=[validators.validate_course])
    # Reference
    reference_category = models.PositiveSmallIntegerField(null=True,
        blank=True, choices=REFERENCE_CATEGORIES)
    reference_name = models.CharField(max_length=202, default='', blank=True,
                                      validators=[validators.validate_reference_name])
    reference_email = models.EmailField(default='', blank=True)
    reference_organization = models.CharField(max_length=200,
        validators=[validators.validate_organization], blank=True)
    reference_title = models.CharField(max_length=60, default='', blank=True,
        validators=[validators.validate_reference_title])
    # 0 1 2 3 = pending, rejected, accepted, withdrawn
    status = models.PositiveSmallIntegerField(default=0, choices=REJECT_ACCEPT_WITHDRAW)
    reference_contact_datetime = models.DateTimeField(null=True)
    reference_response_datetime = models.DateTimeField(null=True)
    # Whether reference verifies the applicant. 0 1 2 = null, no, yes
    reference_response = models.PositiveSmallIntegerField(default=0, choices=REFERENCE_RESPONSES)
    reference_response_text = models.CharField(max_length=2000, validators=[validators.validate_reference_response])
    research_summary = models.CharField(max_length=1000, validators=[validators.validate_research_summary])
    project_of_interest = models.ForeignKey(
        'project.PublishedProject',
        null=True,
        on_delete=models.SET_NULL,
        limit_choices_to={'access_policy': AccessPolicy.CREDENTIALED},
    )
    decision_datetime = models.DateTimeField(null=True)
    responder = models.ForeignKey('user.User', null=True,
        related_name='responded_applications', on_delete=models.SET_NULL)
    responder_comments = models.CharField(max_length=500, default='',
        blank=True)
    revoked_datetime = models.DateTimeField(null=True)

    def file_root(self):
        """Location for storing files associated with the application"""
        return os.path.join(CredentialApplication.FILE_ROOT, self.slug)

    def get_full_name(self):
        return ' '.join([self.first_names, self.last_name])

    def get_latest_by_user(self):
        return CredentialApplication.objects.filter(user=self.user).last()

    def is_latest_by_user(self):
        if self == CredentialApplication.objects.filter(user=self.user).last():
            return True
        else:
            return False

    def is_legacy(self):
        return False

    def time_elapsed(self):
        return (timezone.now() - self.application_datetime).days

    def _apply_decision(self, decision, responder):
        """
        Reject, accept, or withdraw a credentialing application.

        Args:
            decision (int): 1 = reject, 2 = accept, 3 = withdraw.
            responder (str): User object
        """
        self.responder = responder
        self.status = decision
        self.decision_datetime = timezone.now()
        self.save()

    def reject(self, responder):
        """
        Reject a credentialing application.
        """
        self._apply_decision(1, responder)

    def accept(self, responder):
        """
        Reject a credentialing application.
        """
        try:
            with transaction.atomic():
                self._apply_decision(2, responder)
                # update the user credentials
                user = self.user
                user.is_credentialed = True
                user.credential_datetime = timezone.now()
                user.save()
        except DatabaseError:
            messages.error(request, 'Database error. Please try again.')

    def withdraw(self, responder):
        """
        Reject a credentialing application.
        """
        self._apply_decision(3, responder)

    def ref_known_flag(self):
        """
        Returns True if the reference is known, else False. By "Known" we mean
        that the reference has been previously contacted.
        """
        if CredentialApplication.objects.filter(
            reference_email__iexact=self.reference_email,
            reference_contact_datetime__isnull=False).exclude(
            reference_email=''):
            return True
        elif LegacyCredential.objects.filter(
            reference_email__iexact=self.reference_email).exclude(
            reference_email=''):
            return True
        else:
            return False

    def ref_user_flag(self):
        """
        Returns True if the reference is a registered user, else False.
        """
        try:
            ref = User.objects.get(
                    associated_emails__email__iexact=self.reference_email,
                    associated_emails__is_verified=True)
            return True
        except ObjectDoesNotExist:
            return False

    def get_reference_user(self):
        """
        Returns reference User if the reference is a registered user,
        else None.
        """
        try:
            ref = User.objects.get(
                    associated_emails__email__iexact=self.reference_email,
                    associated_emails__is_verified=True)
            return ref
        except ObjectDoesNotExist:
            return None

    def ref_credentialed_flag(self):
        """
        Returns True if the reference is a credentialed registered user,
        else False.
        """
        try:
            ref = User.objects.get(
                    associated_emails__email__iexact=self.reference_email,
                    associated_emails__is_verified=True)
            return ref.is_credentialed
        except ObjectDoesNotExist:
            return False

    def revoke(self):
        """
        Revokes an approved application.
        """
        # Set the application as unsucessful with the current datetime
        self.status = 4
        self.revoked_datetime = timezone.now()

        # Removes credentialing from the user
        self.user.is_credentialed = False
        self.user.credential_datetime = None

        with transaction.atomic():
            self.user.save()
            self.save()

        logger.info('Credentialing for user {0} has been removed.'.format(
            self.user.email))

    def remove_contact_reference(self):
        """
        Remove the date that indicates when the reference was contacted.
        Note that this may also affect the "known" status of the reference.
        """
        self.reference_contact_datetime = None
        self.save()

    def update_review_status(self, review_status):
        """
        Update the review status of a credentialing application.

        Args:

        """
        self.credential_review.status = review_status
        self.credential_review.save()

    def get_review_status(self):
        """
        Get the current review status of a credentialing application. Hacky.
        Could be simplified to return self.credential_review.status later.
        """
        if not hasattr(self, 'credential_review'):
            status = 'Awaiting review'
        elif self.credential_review.status <= 40:
            status = 'Awaiting review'
        elif self.credential_review.status == 50:
            status = 'Awaiting a response from your reference'
        elif self.credential_review.status >= 60:
            status = 'Awaiting final approval'

        return status


class CredentialReview(models.Model):
    """
    Reviews for the CredentialApplications.

    NOTES
    -----
    This relational model will be deleted in the case that a credential
    reviewer decides to "reset" the application, meaning reset it back to the
    "initial review" stage.

    """
    REVIEW_STATUS_LABELS = (
        ('', '-----------'),
        (0,  'Not in review'),
        (10, 'Initial review'),
        (20, 'Training'),
        (30, 'ID check'),
        (40, 'Reference'),
        (50, 'Reference response'),
        (60, 'Final review')
    )

    application = models.OneToOneField('user.CredentialApplication',
                                       related_name='credential_review',
                                       on_delete=models.CASCADE)

    status = models.PositiveSmallIntegerField(default=10,
        choices=REVIEW_STATUS_LABELS)

    # Initial review questions
    fields_complete = models.NullBooleanField(null=True)
    appears_correct = models.NullBooleanField(null=True)
    lang_understandable = models.NullBooleanField(null=True)

    # Training check questions
    citi_report_attached = models.NullBooleanField(null=True)
    training_current = models.NullBooleanField(null=True)
    training_all_modules = models.NullBooleanField(null=True)
    training_privacy_complete = models.NullBooleanField(null=True)
    training_name_match = models.NullBooleanField(null=True)

    # ID check questions
    user_searchable = models.NullBooleanField(null=True)
    user_has_papers = models.NullBooleanField(null=True)
    research_summary_clear = models.NullBooleanField(null=True)
    course_name_provided = models.NullBooleanField(null=True)
    user_understands_privacy = models.NullBooleanField(null=True)
    user_org_known = models.NullBooleanField(null=True)
    user_details_consistent = models.NullBooleanField(null=True)

    # Reference check questions
    ref_appropriate = models.NullBooleanField(null=True)
    ref_searchable = models.NullBooleanField(null=True)
    ref_has_papers = models.NullBooleanField(null=True)
    ref_is_supervisor = models.NullBooleanField(null=True)
    ref_course_list = models.NullBooleanField(null=True)
    ref_skipped = models.NullBooleanField(null=True)

    # Reference response check questions
    ref_knows_applicant = models.NullBooleanField(null=True)
    ref_approves = models.NullBooleanField(null=True)
    ref_understands_privacy = models.NullBooleanField(null=True)

    responder_comments = models.CharField(max_length=500, default='',
                                          blank=True)


class CloudInformation(models.Model):
    """
    Location where the cloud accounts for the user will be stored
    """
    user = models.OneToOneField('user.User', related_name='cloud_information',
        on_delete=models.CASCADE)
    gcp_email = models.OneToOneField('user.AssociatedEmail', related_name='gcp_email',
        on_delete=models.SET_NULL, null=True)
    aws_id = models.CharField(max_length=60, null=True,  blank=True, default=None)
