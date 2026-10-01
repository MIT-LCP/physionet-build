from django.test import TestCase

from project.models import (
    CoreProject,
    ProjectType,
    PublishedAuthor,
    PublishedProject,
)
from search.views import get_content, get_content_normal_search
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
        PublishedAuthor.objects.create(
            user=User.objects.create_user(
                username='coauthor',
                email='coauthor@example.com',
                password='testpass123',
            ),
            project=cls.project1,
            display_order=2,
            first_names='Carol',
            last_name='Danvers',
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
        self.assertEqual(slugs, {'sleep-study'})

    def test_search_title_still_works(self):
        slugs = self._get_slugs(self._search('Cardiac'))
        self.assertEqual(slugs, {'cardiac-signals'})

    def test_search_by_full_name(self):
        slugs = self._get_slugs(self._search('Alice Wonderland'))
        self.assertEqual(slugs, {'cardiac-signals'})

    def test_search_by_two_coauthors(self):
        slugs = self._get_slugs(self._search('Wonderland Danvers'))
        self.assertEqual(slugs, {'cardiac-signals'})

    def test_author_search_combines_with_title(self):
        """A query mixing an author name and a title word should match."""
        slugs = self._get_slugs(self._search('Wonderland Cardiac'))
        self.assertEqual(slugs, {'cardiac-signals'})

    def test_title_match_ranks_above_author_match(self):
        PublishedAuthor.objects.create(
            user=User.objects.create_user(
                username='cardiac',
                email='cardiac@example.com',
                password='testpass123',
            ),
            project=self.project2,
            display_order=2,
            first_names='Dana',
            last_name='Cardiac',
        )
        slugs = list(self._search('Cardiac').values_list('slug', flat=True))
        self.assertEqual(slugs, ['cardiac-signals', 'sleep-study'])


class TestNormalSearchRelevanceScoring(TestCase):
    """Tests that relevance scoring accumulates across all search terms."""

    @classmethod
    def setUpTestData(cls):
        cls.resource_type = ProjectType.objects.get_or_create(
            id=0, defaults={'name': 'Database'}
        )[0]
        cls.project = PublishedProject.objects.create(
            title='Cardiac Signals Database',
            abstract='A collection of cardiac signal recordings.',
            slug='cardiac-signals',
            version='1.0.0',
            submission_slug='cardiac-signals',
            is_latest_version=True,
            resource_type=cls.resource_type,
            core_project=CoreProject.objects.create(),
        )

    def _get_scores(self, term):
        qs = get_content_normal_search(
            [self.resource_type.id], 'relevance', 'desc', term,
        )
        return dict(qs.values_list('slug', 'has_keys'))

    def test_single_term_scores(self):
        scores = self._get_scores('cardiac')
        self.assertGreater(scores.get('cardiac-signals', 0), 0)

    def test_multi_term_accumulates(self):
        """Two matching terms should score higher than one."""
        one_term = self._get_scores('cardiac')
        two_terms = self._get_scores('cardiac signals')
        self.assertGreater(
            two_terms.get('cardiac-signals', 0),
            one_term.get('cardiac-signals', 0),
        )

    def test_trailing_nonmatch_preserves_score(self):
        """A non-matching trailing term must not zero out the score."""
        scores = self._get_scores('cardiac xyznonexistent')
        self.assertGreater(scores.get('cardiac-signals', 0), 0)
