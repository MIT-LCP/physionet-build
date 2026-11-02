import hashlib

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.html import escape


class DepositTermsUnavailable(Exception):
    """
    The deposit terms are turned on, but the static page holding them is
    missing or empty.
    """


def deposit_terms_enabled():
    """
    Whether authors must agree to the deposit terms.
    """
    return bool(settings.DEPOSIT_TERMS_URL)


class DepositTermsVersion(models.Model):
    """
    A copy of the deposit terms, as they were when an author agreed to them.

    The terms are kept on a static page that can be edited in the console,
    and static pages keep no history. Each time someone agrees to the
    terms, the page's current text is stored here (once for each distinct
    text), so we can always show exactly what they agreed to.
    """
    url = models.CharField(max_length=64)
    title = models.CharField(max_length=64)
    content = models.TextField()
    content_hash = models.CharField(max_length=64, unique=True)
    created_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ('created_datetime',)

    def __str__(self):
        return f'{self.title} ({self.created_datetime:%Y-%m-%d}, {self.content_hash[:10]})'

    @classmethod
    def current(cls):
        """
        Return the version matching the deposit terms page as it is now.

        Raises DepositTermsUnavailable if the page is missing or empty.
        """
        from physionet.models import Section, StaticPage

        page = StaticPage.objects.filter(url=settings.DEPOSIT_TERMS_URL).first()
        if page is None:
            raise DepositTermsUnavailable(f'No static page at {settings.DEPOSIT_TERMS_URL}')
        sections = Section.objects.filter(static_page=page).order_by('order')
        if not sections:
            raise DepositTermsUnavailable(f'The static page at {page.url} has no sections')

        content = ''.join(
            f'<h2>{escape(section.title)}</h2>\n{section.content}\n'
            for section in sections
        )
        content_hash = hashlib.sha256(
            '\n'.join([page.url, page.title, content]).encode()
        ).hexdigest()
        version, _ = cls.objects.get_or_create(
            content_hash=content_hash,
            defaults={'url': page.url, 'title': page.title, 'content': content},
        )
        return version


class DepositTermsAcceptance(models.Model):
    """
    A record that an author agreed to the deposit terms for a project.

    Records are never changed or deleted. The submitting author agrees
    when accepting the upload agreement, and each author agrees when
    approving publication. The submitting author may approve on another
    author's behalf, in which case both people are recorded.

    The project is an ActiveProject until publication, when the record
    moves to the PublishedProject.
    """
    class Stage(models.TextChoices):
        UPLOAD = 'upload', 'Upload agreement'
        APPROVAL = 'approval', 'Publication approval'

    terms_version = models.ForeignKey(
        DepositTermsVersion, on_delete=models.PROTECT, related_name='acceptances')
    stage = models.CharField(max_length=16, choices=Stage.choices)

    # The author the agreement applies to
    author_user = models.ForeignKey(
        'user.User', null=True, on_delete=models.SET_NULL,
        related_name='deposit_terms_acceptances')
    author_name = models.CharField(max_length=200)
    author_email = models.EmailField(max_length=255)

    # The person who agreed (the author, or the submitting author on
    # their behalf)
    accepted_by = models.ForeignKey(
        'user.User', null=True, on_delete=models.SET_NULL, related_name='+')
    accepted_by_name = models.CharField(max_length=200)
    on_behalf = models.BooleanField(default=False)

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    accepted_datetime = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ()
        ordering = ('accepted_datetime',)
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return f'{self.author_name} agreed to {self.terms_version} ({self.get_stage_display()})'

    @classmethod
    def record(cls, project, stage, author_user, accepted_by, terms_version):
        """
        Record that author_user agreed to terms_version, with the
        agreement made by accepted_by.
        """
        return cls.objects.create(
            terms_version=terms_version,
            stage=stage,
            author_user=author_user,
            author_name=author_user.get_full_name(ignore_missing_profile=True) or author_user.username,
            author_email=author_user.email,
            accepted_by=accepted_by,
            accepted_by_name=accepted_by.get_full_name(ignore_missing_profile=True) or accepted_by.username,
            on_behalf=(author_user != accepted_by),
            content_type=ContentType.objects.get_for_model(project),
            object_id=project.pk,
        )

    @classmethod
    def for_project(cls, project):
        """
        All agreements for a project, oldest first.
        """
        return cls.objects.filter(
            content_type=ContentType.objects.get_for_model(project),
            object_id=project.pk,
        ).select_related('terms_version')
