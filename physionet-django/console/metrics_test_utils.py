import copy
import csv
from datetime import date, datetime
from io import StringIO
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from console.usage import usage_metrics, usage_sections
from project.models import AccessLog, ActiveProject, Author, DataAccessRequest, PublishedAuthor, PublishedProject
from user.models import CredentialApplication, User


class MetricsTestCase(TestCase):
    fixtures = ['demo-training-type.json', 'demo-user.json', 'site-data.json', 'demo-project.json']

    @classmethod
    def setUpTestData(cls):
        AccessLog.objects.all().delete()
        DataAccessRequest.objects.all().delete()
        ActiveProject.objects.update(submission_datetime=None)
        PublishedProject.objects.update(submission_datetime=None)
        cls.when = timezone.make_aware(datetime(2020, 6, 15, 12))
        cls.dataset = PublishedProject.objects.filter(resource_type_id=0).first()
        PublishedProject.objects.filter(pk=cls.dataset.pk).update(submission_datetime=cls.when)
        cls.dataset.refresh_from_db()
        cls.version = copy.copy(cls.dataset)
        cls.version.pk = None
        cls.version.version = 'usage-test'
        cls.version.submission_slug = 'usage-test'
        cls.version.public_project_uuid = uuid4()
        cls.version.is_latest_version = False
        cls.version.featured = None
        cls.version.save()
        cls.active = ActiveProject.objects.first()
        ActiveProject.objects.filter(pk=cls.active.pk).update(submission_datetime=cls.when)
        cls.active.refresh_from_db()

        cls.viewer = User.objects.create_user('usage-one@example.com', 'password', 'usage-one', is_active=True)
        cls.other = User.objects.create_user('usage-two@example.com', 'password', 'usage-two', is_active=True)
        cls.coauthor = User.objects.create_user('usage-three@example.com', 'password', 'usage-three', is_active=True)
        cls.admin = User.objects.get(email='admin@mit.edu')
        cls.admin.user_permissions.add(Permission.objects.get(codename='can_view_stats'))

        for index, (country, category, status) in enumerate([
            ('BR', 2, CredentialApplication.Status.ACCEPTED),
            ('US', 4, CredentialApplication.Status.ACCEPTED),
            ('GB', 0, CredentialApplication.Status.REJECTED),
        ]):
            application = CredentialApplication.objects.create(
                user=cls.viewer, slug=f'usage-credential-{index}', country=country,
                researcher_category=category, status=status,
                course_category=1 if index == 1 else None,
            )
            CredentialApplication.objects.filter(pk=application.pk).update(
                application_datetime=cls.when + timezone.timedelta(days=index),
            )

        for project in (cls.dataset, cls.version):
            project.authors.all().delete()
            PublishedAuthor.objects.create(project=project, user=cls.viewer, display_order=1, is_submitting=True)
        PublishedAuthor.objects.create(project=cls.dataset, user=cls.coauthor, display_order=2)
        cls.active.authors.all().delete()
        Author.objects.create(project=cls.active, user=cls.other, display_order=1, is_submitting=True)

        for project, user in (
            (cls.dataset, cls.viewer), (cls.dataset, cls.viewer),
            (cls.version, cls.viewer), (cls.version, cls.other),
        ):
            cls.create_log(project, user, cls.when)

    @classmethod
    def create_log(cls, project, user, when, last_access=None):
        log = AccessLog.objects.create(project=project, user=user, count=10)
        AccessLog.objects.filter(pk=log.pk).update(creation_datetime=when, last_access_datetime=last_access or when)
        return log

    def metrics(self, start=date(2020, 1, 1), end=date(2020, 12, 31)):
        return {section['title']: section['rows'] for section in usage_metrics(start, end)}

    def overview(self, metrics):
        return {row['label']: row['count'] for row in metrics['Overview']}

    def create_request(self, user, project=None, status=DataAccessRequest.ACCEPT_REQUEST_VALUE,
                       requested=None, decided=None):
        request = DataAccessRequest.objects.create(
            requester=user, project=project or self.dataset, status=status,
            decision_datetime=decided or self.when,
        )
        DataAccessRequest.objects.filter(pk=request.pk).update(request_datetime=requested or self.when)
        return request

    def credential(self, status, submitted=None, decided=None, **fields):
        app = CredentialApplication.objects.create(
            user=self.viewer, slug=f'operational-{uuid4().hex[:8]}', researcher_category=0,
            status=status, decision_datetime=decided, **fields,
        )
        CredentialApplication.objects.filter(pk=app.pk).update(application_datetime=submitted or self.when)
        return app
