import json
from unittest import mock

import requests
from django.test import TestCase
from django.urls import reverse

from console.utility import generate_doi_payload
from project.citation import CitationLookupError, fetch_citation
from project.models import ActiveProject, PublishedProject, PublishedReference, Reference
from project.test_funding import FIXTURES, bound_form_data, bound_formset_data
from project.validators import find_dois, normalize_doi

CITATION = ('Moody, G. B., &amp; Mark, R. G. (2001). The impact of the MIT-BIH '
            'Arrhythmia Database. <i>IEEE Engineering in Medicine and Biology '
            'Magazine</i>, 20(3), 45–50. https://doi.org/10.1109/51.932724\n')
CLEAN_CITATION = ('Moody, G. B., & Mark, R. G. (2001). The impact of the MIT-BIH '
                  'Arrhythmia Database. IEEE Engineering in Medicine and Biology '
                  'Magazine, 20(3), 45–50. https://doi.org/10.1109/51.932724')


def fake_response(status_code=200, text=CITATION,
                  content_type='text/x-bibliography; style=apa'):
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode('utf-8')
    response.headers['Content-Type'] = content_type
    return response


class TestNormalizeDoi(TestCase):
    def test_prefixes(self):
        for value in ('10.1109/51.932724', ' https://doi.org/10.1109/51.932724 ',
                      'http://dx.doi.org/10.1109/51.932724', 'DOI: 10.1109/51.932724',
                      'doi.org/10.1109/51.932724', '10.1109/51.932724.',
                      'https://www.doi.org/10.1109/51.932724', 'www.doi.org/10.1109/51.932724',
                      'dx.doi.org/10.1109/51.932724'):
            self.assertEqual(normalize_doi(value), '10.1109/51.932724')

    def test_other_values_unchanged(self):
        self.assertEqual(normalize_doi(' not a doi '), 'not a doi')
        self.assertEqual(normalize_doi(None), '')


class TestFetchCitation(TestCase):
    @mock.patch('project.citation.requests.get')
    def test_success(self, mock_get):
        mock_get.return_value = fake_response()
        self.assertEqual(fetch_citation('10.1109/51.932724'), CLEAN_CITATION)
        url = mock_get.call_args.args[0]
        headers = mock_get.call_args.kwargs['headers']
        self.assertEqual(url, 'https://doi.org/10.1109/51.932724')
        self.assertEqual(headers['Accept'], 'text/x-bibliography; style=apa; locale=en-US')

    @mock.patch('project.citation.requests.get')
    def test_not_found(self, mock_get):
        mock_get.return_value = fake_response(404, 'DOI Not Found', 'text/html')
        with self.assertRaisesRegex(CitationLookupError, 'not found'):
            fetch_citation('10.1109/missing')

    @mock.patch('project.citation.requests.get')
    def test_no_citation_available(self, mock_get):
        # A registration agency without content negotiation returns the
        # landing page instead
        mock_get.return_value = fake_response(200, '<html></html>', 'text/html')
        with self.assertRaisesRegex(CitationLookupError, 'No citation'):
            fetch_citation('10.1109/51.932724')

    @mock.patch('project.citation.requests.get', side_effect=requests.ConnectionError)
    def test_connection_error(self, mock_get):
        with self.assertRaisesRegex(CitationLookupError, 'Could not reach'):
            fetch_citation('10.1109/51.932724')


class TestReferenceDisplay(TestCase):
    def test_url_from_doi(self):
        reference = Reference(description='Moody GB. A paper.', doi='10.1109/51.932724')
        self.assertEqual(reference.url, 'https://doi.org/10.1109/51.932724')
        self.assertEqual(
            reference.html_description,
            'Moody GB. A paper. <a href="https://doi.org/10.1109/51.932724">'
            'https://doi.org/10.1109/51.932724</a>')

    def test_doi_link_in_citation_not_repeated(self):
        reference = Reference(description='A paper. https://doi.org/10.1109/51.932724',
                              doi='10.1109/51.932724')
        self.assertEqual(reference.html_description.count('https://doi.org/'), 2)

    def test_doi_link_in_citation_differs_in_case(self):
        reference = Reference(description='A paper. https://doi.org/10.13026/c2xw26',
                              doi='10.13026/C2XW26')
        self.assertEqual(reference.html_description.count('https://doi.org/'), 2)

    def test_doi_in_citation_with_other_prefix(self):
        # The DOI written in the citation is linked, not added again
        link = ('<a href="https://doi.org/10.13026/C2XW26">'
                'https://doi.org/10.13026/C2XW26</a>')
        for written in ('doi:10.13026/C2XW26', 'DOI: 10.13026/c2xw26',
                        'http://dx.doi.org/10.13026/C2XW26', 'https://www.doi.org/10.13026/C2XW26'):
            reference = Reference(description='Pollard TJ (2016). MIMIC-III. ' + written + '.',
                                  doi='10.13026/C2XW26')
            self.assertEqual(reference.html_description,
                             'Pollard TJ (2016). MIMIC-III. ' + link + '.')

        # A published reference whose stored link is the old form
        reference = PublishedReference(
            description='Pollard TJ (2016). MIMIC-III. http://dx.doi.org/10.13026/C2XW26',
            url='http://dx.doi.org/10.13026/C2XW26', doi='10.13026/C2XW26')
        self.assertEqual(reference.html_description.count('<a '), 1)

    def test_doi_in_publisher_link_left_alone(self):
        # The DOI link is added, and the publisher's link is not changed
        reference = Reference(
            description='A paper (2020). https://example.org/doi/10.13026/C2XW26',
            doi='10.13026/C2XW26')
        self.assertEqual(
            reference.html_description,
            'A paper (2020). https://example.org/doi/10.13026/C2XW26 '
            '<a href="https://doi.org/10.13026/C2XW26">https://doi.org/10.13026/C2XW26</a>')

    def test_published_url_fits_doi_link(self):
        # Publishing stores the DOI link (or a URL from the citation)
        url_length = PublishedReference._meta.get_field('url').max_length
        self.assertGreaterEqual(
            url_length, len('https://doi.org/') + Reference._meta.get_field('doi').max_length)
        self.assertGreaterEqual(url_length, Reference._meta.get_field('description').max_length)

    def test_url_without_doi(self):
        reference = Reference(description='A <site>: https://example.org/page')
        self.assertEqual(reference.url, 'https://example.org/page')
        self.assertEqual(
            reference.html_description,
            'A &lt;site&gt;: <a href="https://example.org/page">https://example.org/page</a>')

    def test_no_url(self):
        reference = Reference(description='A book & more.')
        self.assertIsNone(reference.url)
        self.assertEqual(reference.html_description, 'A book &amp; more.')


class TestReferenceSubmission(TestCase):
    fixtures = FIXTURES

    AUTHOR = 'rgmark@mit.edu'
    PASSWORD = 'Tester11!'
    PROJECT_TITLE = 'MIT-BIH Arrhythmia Database'

    def setUp(self):
        self.project = ActiveProject.objects.get(title=self.PROJECT_TITLE)
        self.url = reverse('project_content', args=(self.project.slug,))
        self.lookup_url = reverse('reference_doi_lookup', args=(self.project.slug,))
        self.client.login(username=self.AUTHOR, password=self.PASSWORD)

    def content_data(self, reference_rows=()):
        """
        POST data for the content page, with extra reference rows added.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        context = response.context
        data = bound_form_data(context['description_form'])
        reference_formset = context['reference_formset']
        data.update(bound_formset_data(reference_formset))

        prefix = reference_formset.prefix
        start = len(reference_formset.forms)
        for i, row in enumerate(reference_rows, start=start):
            for key, value in row.items():
                data[f'{prefix}-{i}-{key}'] = value
        data[f'{prefix}-TOTAL_FORMS'] = start + len(reference_rows)
        return data

    def test_content_page_has_lookup(self):
        Reference.objects.create(project=self.project, description='A paper.', order=1)
        response = self.client.get(self.url)
        self.assertContains(response, 'doi-lookup-button')
        self.assertContains(response, f'data-lookup-url="{self.lookup_url}"')

    def test_add_reference_with_doi(self):
        data = self.content_data(reference_rows=[
            {'doi': ' https://doi.org/10.1109/51.932724 ',
             'description': '  Moody GB,   Mark RG. A paper. '},
        ])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Your project content has been updated.')
        reference = self.project.references.get(doi='10.1109/51.932724')
        self.assertEqual(reference.description, 'Moody GB, Mark RG. A paper.')
        snapshot = self.project.submission_metadata_snapshot()
        self.assertIn({'order': reference.order, 'description': reference.description,
                       'doi': '10.1109/51.932724'}, snapshot['references'])

    def test_add_reference_without_doi(self):
        data = self.content_data(reference_rows=[{'doi': '', 'description': 'A book.'}])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Your project content has been updated.')
        self.assertEqual(self.project.references.get(description='A book.').doi, '')

    def test_invalid_doi(self):
        data = self.content_data(reference_rows=[
            {'doi': 'https://example.org/paper', 'description': 'A paper.'},
        ])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Invalid DOI')
        self.assertFalse(self.project.references.filter(description='A paper.').exists())

    def test_duplicate_doi(self):
        data = self.content_data(reference_rows=[
            {'doi': '10.1109/51.932724', 'description': 'A paper.'},
            {'doi': 'doi:10.1109/51.932724', 'description': 'The same paper.'},
        ])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Each DOI may only be used for one reference.')
        self.assertFalse(self.project.references.filter(doi='10.1109/51.932724').exists())

    def test_add_first_reference_form(self):
        self.project.references.all().delete()
        response = self.client.get(
            reverse('edit_content_item', args=(self.project.slug,)),
            {'item': 'reference', 'add_first': 'true'})
        self.assertContains(response, 'DOI (optional)')
        self.assertContains(response, f'data-lookup-url="{self.lookup_url}"')

    @mock.patch('project.citation.requests.get')
    def test_lookup(self, mock_get):
        mock_get.return_value = fake_response()
        response = self.client.get(self.lookup_url, {'doi': 'https://doi.org/10.1109/51.932724'})
        self.assertEqual(response.json(), {'doi': '10.1109/51.932724', 'citation': CLEAN_CITATION})

    @mock.patch('project.citation.requests.get')
    def test_lookup_errors(self, mock_get):
        response = self.client.get(self.lookup_url, {'doi': ''})
        self.assertEqual(response.json(), {'error': 'Enter a DOI.'})
        response = self.client.get(self.lookup_url, {'doi': 'not a doi'})
        self.assertEqual(response.json(), {'error': 'This is not a valid DOI.'})
        mock_get.assert_not_called()

        mock_get.return_value = fake_response(404, 'DOI Not Found', 'text/html')
        response = self.client.get(self.lookup_url, {'doi': '10.1109/missing'})
        self.assertEqual(response.json(), {'error': 'This DOI was not found.'})

        mock_get.return_value = fake_response(text='x' * 1001)
        response = self.client.get(self.lookup_url, {'doi': '10.1109/51.932724'})
        self.assertIn('too long', response.json()['error'])

    @mock.patch('project.citation.requests.get')
    def test_lookup_requires_edit_access(self, mock_get):
        # A co-author who is not the submitting author
        self.client.login(username='aewj@mit.edu', password=self.PASSWORD)
        response = self.client.get(self.lookup_url, {'doi': '10.1109/51.932724'})
        self.assertEqual(response.status_code, 404)

        self.client.logout()
        response = self.client.get(self.lookup_url, {'doi': '10.1109/51.932724'})
        self.assertEqual(response.status_code, 302)
        mock_get.assert_not_called()


class TestFindDois(TestCase):
    def test_find_dois(self):
        self.assertEqual(
            find_dois('See https://doi.org/10.1109/51.932724. Also doi:10.13026/C2XW26, and more.'),
            ['10.1109/51.932724', '10.13026/c2xw26'])
        self.assertEqual(find_dois('No identifier, 2001.'), [])


class TestQualityWarnings(TestCase):
    def warnings(self, description, doi=''):
        return Reference(description=description, doi=doi).quality_warnings()

    def test_good_references(self):
        self.assertEqual(self.warnings('Moody GB (2001). A paper.', doi='10.1109/51.932724'), [])
        self.assertEqual(self.warnings('Moody GB (2001). A paper. https://doi.org/10.1109/51.932724',
                                       doi='10.1109/51.932724'), [])
        self.assertEqual(self.warnings('PhysioNet. (n.d.). WFDB. https://physionet.org/wfdb/'), [])
        self.assertEqual(self.warnings('Moody GB (2001b). A paper. https://example.org'), [])

    def test_no_year(self):
        self.assertEqual(self.warnings('https://physionet.org/physiotools/wag/'),
                         ['has no publication year'])
        # Digits in DOIs and links are not mistaken for a year
        self.assertEqual(self.warnings('A paper. https://example.org/2016/paper',
                                       doi='10.1001/jama.2016.0287'),
                         ['has no publication year'])

    def test_no_link(self):
        self.assertEqual(self.warnings('Collins FS. A comment. Nature 505, 612 (2014).'),
                         ['has no DOI or URL'])

    def test_doi_in_citation_only(self):
        self.assertEqual(
            self.warnings('Pollard TJ. MIMIC-III http://dx.doi.org/10.13026/C2XW26 (2016)'),
            ['has a DOI in the citation, which should also be entered in the DOI box'])
        self.assertEqual(
            self.warnings('Pollard TJ (2016). MIMIC-III. doi:10.13026/C2XW26'),
            ['has a DOI in the citation, which should also be entered in the DOI box'])

    def test_doi_mismatch(self):
        self.assertEqual(
            self.warnings('Pollard TJ (2016). MIMIC-III. https://doi.org/10.13026/C2XW26',
                          doi='10.1109/51.932724'),
            ['has a DOI in the citation that does not match the DOI box'])
        # DOIs are not case sensitive
        self.assertEqual(
            self.warnings('Pollard TJ (2016). MIMIC-III. https://doi.org/10.13026/c2xw26',
                          doi='10.13026/C2XW26'), [])


class TestReferenceWarningDisplay(TestCase):
    fixtures = FIXTURES

    def setUp(self):
        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        Reference.objects.create(project=self.project, order=1,
                                 description='Moody GB (2001). A paper.', doi='10.1109/51.932724')
        Reference.objects.create(project=self.project, order=2,
                                 description='https://physionet.org/physiotools/wag/')

    def test_integrity_warnings(self):
        self.assertTrue(self.project.check_integrity())
        self.assertIn('Reference 2 has no publication year.', self.project.integrity_warnings)
        self.assertFalse(any(w.startswith('Reference 1 ') for w in self.project.integrity_warnings))

        response = self.client.get(reverse('check_integrity', args=(self.project.slug,)))
        self.assertTrue(response.json()['passes_checks'])
        self.assertIn('Reference 2 has no publication year.', response.json()['integrity_warnings'])

    def test_content_page(self):
        response = self.client.get(reverse('project_content', args=(self.project.slug,)))
        self.assertContains(response, 'This reference has no publication year.', count=1)


class TestReferenceMetadata(TestCase):
    fixtures = FIXTURES

    def setUp(self):
        self.project = PublishedProject.objects.get(slug='demoeicu', version='2.0.0')
        self.project.references.create(description='Moody GB (2001). A </script> paper.',
                                       doi='10.1109/51.932724', url='https://doi.org/10.1109/51.932724',
                                       order=1)
        self.project.references.create(description='A copy of the same paper.',
                                       doi='10.1109/51.932724', order=2)
        self.project.references.create(description='Pollard TJ (2016). MIMIC-III.',
                                       doi='10.13026/C2XW26', order=3)

    def test_datacite_payload(self):
        payload = generate_doi_payload(self.project, event='publish')
        related = payload['data']['attributes']['relatedIdentifiers']
        self.assertEqual(
            [r for r in related if r['relationType'] == 'References'], [
                {'relationType': 'References', 'relatedIdentifier': '10.1109/51.932724',
                 'relatedIdentifierType': 'DOI'},
                {'relationType': 'References', 'relatedIdentifier': '10.13026/C2XW26',
                 'relatedIdentifierType': 'DOI'},
            ])
        # The version relation is kept
        self.assertEqual(related[0]['relationType'], 'IsVersionOf')

    def test_draft_payload_for_active_project(self):
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        Reference.objects.create(project=project, description='A paper.', doi='10.1109/51.932724', order=1)
        payload = generate_doi_payload(project, event='draft')
        self.assertEqual(payload['data']['attributes']['relatedIdentifiers'], [
            {'relationType': 'References', 'relatedIdentifier': '10.1109/51.932724',
             'relatedIdentifierType': 'DOI'},
        ])

    def test_schema_org_citation(self):
        response = self.client.get(reverse('published_project',
                                           args=(self.project.slug, self.project.version)))
        content = response.content.decode()
        start = content.index('<script type="application/ld+json">') + len(
            '<script type="application/ld+json">')
        end = content.index('</script>', start)
        citation = json.loads(content[start:end])['citation']
        # The demo references have no order, so their position depends
        # on the database
        works = {work['name']: work for work in citation}
        self.assertEqual(len(citation), 5)
        self.assertEqual(works['Moody GB (2001). A </script> paper.'], {
            '@type': 'CreativeWork', 'name': 'Moody GB (2001). A </script> paper.',
            'identifier': 'https://doi.org/10.1109/51.932724',
            'url': 'https://doi.org/10.1109/51.932724',
        })
        url = 'https://eicu-crd.mit.edu/eicutables/apachepatientresult/'
        self.assertEqual(works[url], {'@type': 'CreativeWork', 'name': url, 'url': url})
