from django.test import TestCase
from django.utils.html import escape
from django.urls import reverse


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
