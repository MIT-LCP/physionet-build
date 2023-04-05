import os
import textwrap
import urllib.parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.redirects.models import Redirect
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils.regex_helper import normalize

from user.test_views import TestMixin


class TestURLs(TestMixin):
    """
    Test all application-defined URL patterns.

    This test case walks through the URL patterns that are registered
    with Django, and tries to perform an ordinary GET request for each
    pattern.

    Since URL patterns can accept parameters in the URL, the values of
    these parameters must be set by defining a variable TEST_DEFAULTS
    in urls.py.

    For example, if urls.py contains:

        urlpatterns = [
            path('projects/', views.project_home, name='project_home'),
            path('projects/<project_slug>/', views.project_overview,
                 name='project_overview'),
            path('projects/<project_slug>/preview/', views.project_preview,
                 name='project_preview'),
        ]

        TEST_DEFAULTS = {
            'project_slug': 'asdfghjk',
        }

    then this class would attempt to test the URLs:

        /projects/
        /projects/asdfghjk/
        /projects/asdfghjk/preview/

    The values in TEST_DEFAULTS can be overridden for a particular URL
    pattern by defining a variable TEST_CASES.  This also allows
    testing the same URL pattern with varying arguments.  For example:

        TEST_CASES = {
            'project_preview': [
                {'project_slug': 'one'},
                {'project_slug': 'two'},
            ],
        }

    would result in the following URLs being tested:

        /projects/
        /projects/asdfghjk/
        /projects/one/preview/
        /projects/two/preview/

    Additional special parameters can also be set in TEST_DEFAULTS and
    TEST_CASES:

    - '_user_' may be set to a username in order to view the page as a
      logged-in user.

    - '_query_' may be set to a dictionary in order to pass query
      parameters.

    - '_skip_' may be set to a boolean, or a function returning a
      boolean, in order to skip testing the given URL under some
      conditions.
    """
    def setUp(self):
        super().setUp()

        # If this environment variable is set, we will store the
        # rendered contents of each view in this directory.  For
        # example, if PHYSIONET_TEST_HTML_DIR is '/tmp/example-html',
        # then the contents of the URL '/about/' will be saved as
        # '/tmp/example-html/about/index.html'.
        self._dump_dir = os.environ.get('PHYSIONET_TEST_HTML_DIR', None)
        if self._dump_dir is not None:
            self._dump_dir = os.path.realpath(self._dump_dir)

    def _find_test_cases(self, prefix, resolver):
        """
        Enumerate possible URLs from a URLResolver.

        This function walks through the URL patterns defined by the
        application and returns an iterable of test cases.

        """
        # Find the example parameters for the current urlconf module.
        TEST_DEFAULTS = getattr(resolver.urlconf_module, 'TEST_DEFAULTS', None)
        TEST_CASES = getattr(resolver.urlconf_module, 'TEST_CASES', {})

        for url_pattern in resolver.url_patterns:
            path = prefix + url_pattern.pattern.regex.pattern.lstrip('^')
            if isinstance(url_pattern, URLResolver):
                # include() path: recurse into the included module
                yield from self._find_test_cases(path, url_pattern)

            elif isinstance(url_pattern, URLPattern):
                test_cases = TEST_CASES.get(url_pattern.name, {})
                if TEST_DEFAULTS is None and not test_cases:
                    continue

                if isinstance(test_cases, dict):
                    test_cases = [test_cases]

                for pattern, _ in normalize(path):
                    for args in test_cases:
                        if TEST_DEFAULTS is not None:
                            args = {**TEST_DEFAULTS, **args}
                        yield (resolver.urlconf_module, url_pattern.name,
                               pattern, args)

    def test_urls(self):
        resolver = get_resolver()
        for mod, name, pattern, args in self._find_test_cases('/', resolver):
            with self.subTest(pattern, **args):
                try:
                    url = pattern % args
                except KeyError as exc:
                    message = textwrap.dedent("""
                        Missing {parameter!r} for {name} in {module}
                        (URL: {pattern!r})

                        Note: you probably need to add something like this in
                        {source_file}:

                            TEST_DEFAULTS = {{
                                {parameter!r}: 'something',
                                ...
                            }}

                        or else:

                            TEST_CASES = {{
                                {name!r}: {{
                                    {parameter!r}: 'something',
                                    ...
                                }},
                                ...
                            }}
                    """).lstrip('\n').format(
                        name=name, parameter=exc.args[0], pattern=pattern,
                        module=mod.__name__, source_file=mod.__file__)
                    raise Exception(message) from None

                try:
                    self._handle_request(url, **args)
                except RedirectedToLogin:
                    message = textwrap.dedent("""
                        Login required for {name} in {module}
                        (URL: {url!r})

                        Note: you probably need to add something like this in
                        {source_file}:

                            TEST_CASES = {{
                                {name!r}: {{
                                    '_user_': 'somebody',
                                    ...
                                }},
                                ...
                            }}
                    """).lstrip('\n').format(
                        name=name, url=url,
                        module=mod.__name__, source_file=mod.__file__)
                    raise Exception(message) from None

    def _handle_request(self, url, _user_=None, _query_={}, _skip_=False,
                        **kwargs):
        if callable(_skip_):
            _skip_ = _skip_()
        if _skip_:
            self.skipTest("skipped by TEST_CASES")

        if _user_ is None:
            self.client.logout()
        else:
            user = get_user_model().objects.get_by_natural_key(_user_)
            self.client.force_login(user)

        response = self.client.get(url, _query_)
        self.assertGreaterEqual(response.status_code, 200)
        self.assertLess(response.status_code, 400)

        # Assume if we are redirected to LOGIN_URL, that means we
        # don't have permission to view this page.  An appropriate
        # _user_ should be specified.
        location = response.headers.get('Location', '')
        if urllib.parse.urlparse(location).path == settings.LOGIN_URL:
            raise RedirectedToLogin

        if self._dump_dir is not None:
            path = self._output_filename(url, _query_, response)
            path = os.path.join(self._dump_dir, path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(response.content)

    def _output_filename(self, url, query, response):
        path = url
        if path.endswith('/'):
            default_suffix = {
                'application/javascript': '.js',
                'application/json': '.json',
                'text/html': '.html',
                'text/plain': '.txt',
            }
            content_type = response.get('Content-Type').split(';')[0]
            path += 'index' + default_suffix.get(content_type, '')
        if query:
            path += '?' + urllib.parse.urlencode(query)
        return path.lstrip('/')


class RedirectedToLogin(Exception):
    """Exception raised if a URL redirects to the login page."""
    pass


class TestRedirect(TestCase):
    """
    Test the redirect app.

    This test case attempts to access a non-existent URL, which raises a 404.
    We then set up a redirect on the URL, and test that the redirect works as
    expected.
    """
    def _add_redirect(self, site_id=1, old_path='/contact-us/', new_path='/contact/'):
        """
        Adds a redirect to test.
        """
        Redirect.objects.create(site_id=site_id,
                                old_path=old_path,
                                new_path=new_path)

    def test_redirect(self):
        """
        Creates and tests a redirect.
        """
        site_id = settings.SITE_ID
        old_path = '/redirect/me/'
        new_path = '/news/'

        response = self.client.get(old_path)
        self.assertEqual(response.status_code, 404)

        self._add_redirect(site_id=site_id, old_path=old_path, new_path=new_path)

        response = self.client.get(old_path)
        self.assertEqual(response.status_code, 301)
