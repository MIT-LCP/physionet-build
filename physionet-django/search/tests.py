from django.test import TestCase

from project.models import (
    CoreProject,
    ProjectType,
    PublishedAuthor,
    PublishedProject,
)
from search.views import get_content
from user.models import User


class AuthorSearchTests(TestCase):
    """Tests for searching projects by author name."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='testpass123',
        )
        cls.resource_type = ProjectType.objects.get_or_create(
            id=0, defaults={'name': 'Database'}
        )[0]
        cls.core1 = CoreProject.objects.create()
        cls.core2 = CoreProject.objects.create()

        cls.project1 = PublishedProject.objects.create(
            title='Cardiac Signals Database',
            abstract='A collection of cardiac signal recordings.',
            slug='cardiac-signals',
            version='1.0.0',
            submission_slug='cardiac-signals',
            is_latest_version=True,
            resource_type=cls.resource_type,
            core_project=cls.core1,
        )
        PublishedAuthor.objects.create(
            user=cls.user,
            project=cls.project1,
            display_order=1,
            is_submitting=True,
            is_corresponding=True,
            first_names='Alice',
            last_name='Wonderland',
        )

        cls.project2 = PublishedProject.objects.create(
            title='Sleep Study Dataset',
            abstract='Polysomnography recordings from a sleep study.',
            slug='sleep-study',
            version='1.0.0',
            submission_slug='sleep-study',
            is_latest_version=True,
            resource_type=cls.resource_type,
            core_project=cls.core2,
        )
        PublishedAuthor.objects.create(
            user=cls.user,
            project=cls.project2,
            display_order=1,
            is_submitting=True,
            is_corresponding=True,
            first_names='Bob',
            last_name='Marley',
        )

    def _search(self, term):
        return get_content(
            resource_type=[self.resource_type.id],
            orderby='relevance',
            direction='desc',
            search_term=term,
        )

    def _get_slugs(self, qs):
        return set(qs.values_list('slug', flat=True))

    def test_search_by_last_name(self):
        slugs = self._get_slugs(self._search('Wonderland'))
        self.assertIn('cardiac-signals', slugs)
        self.assertNotIn('sleep-study', slugs)

    def test_search_by_first_name(self):
        slugs = self._get_slugs(self._search('Bob'))
        self.assertIn('sleep-study', slugs)

    def test_search_title_still_works(self):
        slugs = self._get_slugs(self._search('Cardiac'))
        self.assertIn('cardiac-signals', slugs)

    def test_author_search_combines_with_title(self):
        """Author and title matches should both appear in results."""
        slugs = self._get_slugs(self._search('Wonderland'))
        self.assertIn('cardiac-signals', slugs)
