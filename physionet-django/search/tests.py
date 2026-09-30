from django.test import TestCase

from project.models import (
    CoreProject,
    ProjectType,
    PublishedAuthor,
    PublishedProject,
)
from search.templatetags.search_tags import highlight
from search.views import get_content, split_search_terms
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


class TestSplitSearchTerms(TestCase):
    """Tests for the shared search term splitting function."""

    def test_whitespace(self):
        self.assertEqual(split_search_terms('acute episodes'), ['acute', 'episodes'])

    def test_commas(self):
        self.assertEqual(split_search_terms('ecg,eeg'), ['ecg', 'eeg'])

    def test_semicolons(self):
        self.assertEqual(split_search_terms('ecg;eeg'), ['ecg', 'eeg'])

    def test_mixed_delimiters(self):
        self.assertEqual(split_search_terms('ecg, eeg; heart'), ['ecg', 'eeg', 'heart'])

    def test_extra_whitespace(self):
        self.assertEqual(split_search_terms('  ecg   eeg  '), ['ecg', 'eeg'])

    def test_empty_string(self):
        self.assertEqual(split_search_terms(''), [])

    def test_none(self):
        self.assertEqual(split_search_terms(None), [])

    def test_single_term(self):
        self.assertEqual(split_search_terms('ecg'), ['ecg'])


class TestHighlightFilter(TestCase):
    """Tests for the highlight template filter."""

    def test_single_term(self):
        result = highlight('Predicting Acute Hypotensive Episodes', 'acute')
        self.assertIn('<mark>Acute</mark>', result)
        self.assertIn('Predicting', result)

    def test_multiple_terms(self):
        result = highlight('Predicting Acute Hypotensive Episodes', 'acute episodes')
        self.assertIn('<mark>Acute</mark>', result)
        self.assertIn('<mark>Episodes</mark>', result)

    def test_case_insensitive(self):
        result = highlight('ECG Database', 'ecg')
        self.assertIn('<mark>ECG</mark>', result)

    def test_no_match(self):
        result = highlight('Some title', 'xyz')
        self.assertEqual(result, 'Some title')

    def test_empty_search_term(self):
        result = highlight('Some title', '')
        self.assertEqual(result, 'Some title')

    def test_none_search_term(self):
        result = highlight('Some title', None)
        self.assertEqual(result, 'Some title')

    def test_html_escaping(self):
        """Ensure HTML in text is escaped, not rendered."""
        result = highlight('<script>alert("xss")</script>', 'script')
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;<mark>script</mark>&gt;', result)

    def test_special_regex_chars_dot(self):
        """Dot in search term is treated as literal, not regex wildcard."""
        result = highlight('version 2.0 release and 200 items', '2.0')
        self.assertIn('<mark>2.0</mark>', result)
        self.assertNotIn('<mark>200</mark>', result)

    def test_special_regex_chars_parens(self):
        """Parentheses in search term are treated as literals."""
        result = highlight('function foo() is defined', 'foo()')
        self.assertIn('<mark>foo()</mark>', result)

    def test_html_entities_in_text(self):
        """Text with characters that become HTML entities after escaping."""
        result = highlight('A & B are <partners>', 'B')
        self.assertNotIn('<partners>', result)
        self.assertIn('<mark>B</mark>', result)
