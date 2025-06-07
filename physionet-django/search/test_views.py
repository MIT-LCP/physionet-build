from django.test import TestCase
from django.utils.html import escape
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from project.models import PublishedProject
from .views import get_content_postgres_full_text_search, get_content_normal_search


class TestProjectSearch(TestCase):
    """
    Tests for the project search engine.
    """

    def test_search_content(self):
        """
        Test the main content index.
        """
        url = reverse('content_index')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assert_link(response, '/content/demobsn/1.0/')
        self.assert_link(response, '/content/demoecg/10.5.24/')
        self.assert_link(response, '/content/demoeicu/2.0.0/')
        self.assert_link(response, '/content/demopsn/1.0/')
        self.assert_link(response, '/content/demoselfmanaged/1.0.0/')

        # word found in title/abstract
        response = self.client.get(url + '?topic=challenge')
        self.assertEqual(response.status_code, 200)
        self.assert_link(response, '/content/demobsn/1.0/')
        self.assert_no_link(response, '/content/demoecg/10.5.24/')
        self.assert_no_link(response, '/content/demoeicu/2.0.0/')
        self.assert_no_link(response, '/content/demopsn/1.0/')
        self.assert_no_link(response, '/content/demoselfmanaged/1.0.0/')

        # word not found anywhere
        response = self.client.get(url + '?topic=fnord')
        self.assertEqual(response.status_code, 200)
        self.assert_no_link(response, '/content/demobsn/1.0/')
        self.assert_no_link(response, '/content/demoecg/10.5.24/')
        self.assert_no_link(response, '/content/demoeicu/2.0.0/')
        self.assert_no_link(response, '/content/demopsn/1.0/')
        self.assert_no_link(response, '/content/demoselfmanaged/1.0.0/')

        # restricted to type 1 (software)
        response = self.client.get(url + '?types=1')
        self.assertEqual(response.status_code, 200)
        self.assert_no_link(response, '/content/demobsn/1.0/')
        self.assert_link(response, '/content/demoecg/10.5.24/')
        self.assert_no_link(response, '/content/demoeicu/2.0.0/')
        self.assert_link(response, '/content/demopsn/1.0/')
        self.assert_no_link(response, '/content/demoselfmanaged/1.0.0/')

        # restricted to types 0/1 with a word that is only found in 'demobsn'
        response = self.client.get(url + '?topic=challenge&types=0&types=1')
        self.assertEqual(response.status_code, 200)
        self.assert_no_link(response, '/content/demobsn/1.0/')
        self.assert_no_link(response, '/content/demoecg/10.5.24/')
        self.assert_no_link(response, '/content/demoeicu/2.0.0/')
        self.assert_no_link(response, '/content/demopsn/1.0/')
        self.assert_no_link(response, '/content/demoselfmanaged/1.0.0/')

        # invalid arguments
        response = self.client.get(url + '?types=asdfghjk')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(url + '?orderby=asdfghjk')
        self.assertEqual(response.status_code, 200)

    def test_search_database(self):
        """
        Test the database index.
        """
        url = reverse('database_index')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assert_no_link(response, '/content/demobsn/1.0/')
        self.assert_no_link(response, '/content/demoecg/10.5.24/')
        self.assert_link(response, '/content/demoeicu/2.0.0/')
        self.assert_no_link(response, '/content/demopsn/1.0/')
        self.assert_link(response, '/content/demoselfmanaged/1.0.0/')

        # word not found in any database projects
        response = self.client.get(url + '?topic=challenge')
        self.assertEqual(response.status_code, 200)
        self.assert_no_link(response, '/content/demobsn/1.0/')
        self.assert_no_link(response, '/content/demoecg/10.5.24/')
        self.assert_no_link(response, '/content/demoeicu/2.0.0/')
        self.assert_no_link(response, '/content/demopsn/1.0/')
        self.assert_no_link(response, '/content/demoselfmanaged/1.0.0/')

        # invalid arguments
        response = self.client.get(url + '?types=asdfghjk')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(url + '?orderby=asdfghjk')
        self.assertEqual(response.status_code, 200)

    def assert_link(self, response, url):
        """
        Assert that a response contains a link to a given URL.

        The body of the response must contain the exact string
        '<a href="X"', where X is the HTML-escaped URL.  Other links
        will not be recognized.
        """
        link = '<a href="{}"'.format(escape(url))
        self.assertIn(link.encode(), response.content)

    def assert_no_link(self, response, url):
        """
        Assert that a response does not contain a link to a given URL.

        The body of the response must not contain the exact string
        '<a href="X"', where X is the HTML-escaped URL.  Other links
        will be ignored.
        """
        link = '<a href="{}"'.format(escape(url))
        self.assertNotIn(link.encode(), response.content)


class TestProjectSearchEngine(TestCase):
    def setUp(self):
        # Create test projects with various content
        self.project1 = PublishedProject.objects.create(
            title="Machine Learning ECG Analysis",
            abstract="Deep learning approach for ECG signal processing",
            resource_type="Project",
            is_latest_version=True,
            publish_datetime=timezone.now()
        )
        self.project1.topics.create(description="Machine Learning")
        self.project1.topics.create(description="ECG")

        self.project2 = PublishedProject.objects.create(
            title="ECG Database",
            abstract="Collection of ECG recordings",
            resource_type="Project",
            is_latest_version=True,
            publish_datetime=timezone.now() - timezone.timedelta(days=1)
        )
        self.project2.topics.create(description="ECG")
        self.project2.topics.create(description="Database")

        self.project3 = PublishedProject.objects.create(
            title="Deep Learning Tutorial",
            abstract="Introduction to deep learning concepts",
            resource_type="Project",
            is_latest_version=True,
            publish_datetime=timezone.now() - timezone.timedelta(days=2)
        )
        self.project3.topics.create(description="Deep Learning")
        self.project3.topics.create(description="Tutorial")

    def test_exact_phrase_matching(self):
        """Test exact phrase matching in search"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="machine learning"
        )
        self.assertEqual(results.first().id, self.project1.id)

    def test_partial_word_matching(self):
        """Test partial word matching in search"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="learn"
        )
        self.assertIn(self.project1.id, results.values_list('id', flat=True))
        self.assertIn(self.project3.id, results.values_list('id', flat=True))

    def test_multi_word_search(self):
        """Test multi-word search with different combinations"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="deep ecg"
        )
        self.assertEqual(results.first().id, self.project1.id)

    def test_relevance_scoring(self):
        """Test that relevance scoring prioritizes better matches"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="ecg"
        )
        # Project with "ECG" in title should rank higher than one with it in abstract
        self.assertEqual(results.first().id, self.project2.id)

    def test_normal_search_exact_matches(self):
        """Test exact matching in normal search"""
        results = get_content_normal_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="machine learning"
        )
        self.assertEqual(results.first().id, self.project1.id)

    def test_normal_search_partial_matches(self):
        """Test partial matching in normal search"""
        results = get_content_normal_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="learn"
        )
        self.assertIn(self.project1.id, results.values_list('id', flat=True))
        self.assertIn(self.project3.id, results.values_list('id', flat=True))

    def test_normal_search_relevance_scoring(self):
        """Test relevance scoring in normal search"""
        results = get_content_normal_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="ecg"
        )
        # Project with "ECG" in title should rank higher
        self.assertEqual(results.first().id, self.project2.id)

    def test_search_term_normalization(self):
        """Test that search terms are properly normalized"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="  Machine  Learning  "
        )
        self.assertEqual(results.first().id, self.project1.id)

    def test_empty_search_terms(self):
        """Test handling of empty search terms"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term=""
        )
        self.assertEqual(results.count(), 3)

    def test_special_characters(self):
        """Test handling of special characters in search terms"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="machine-learning"
        )
        self.assertIn(self.project1.id, results.values_list('id', flat=True))

    def test_case_insensitivity(self):
        """Test case insensitivity in search"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="MACHINE LEARNING"
        )
        self.assertEqual(results.first().id, self.project1.id)

    def test_combined_search_strategies(self):
        """Test that different search strategies work together"""
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="relevance",
            direction="desc",
            search_term="deep learning ecg"
        )
        # Should find project1 due to combined relevance of terms
        self.assertEqual(results.first().id, self.project1.id)

    def test_sorting_options(self):
        """Test different sorting options"""
        # Test sorting by publish date
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="publish_datetime",
            direction="desc",
            search_term="learning"
        )
        self.assertEqual(results.first().id, self.project1.id)

        # Test sorting by title
        results = get_content_postgres_full_text_search(
            resource_type=["Project"],
            orderby="title",
            direction="asc",
            search_term="learning"
        )
        self.assertEqual(results.first().id, self.project3.id)
