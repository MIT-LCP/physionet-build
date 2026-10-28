import json

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from console.utility import generate_doi_payload
from project.models import ActiveProject, Funding, PublishedProject, SubmissionStatus
from project.validators import normalize_funder_identifier, validate_funder_identifier
from user.models import User
from user.test_views import TestMixin

FIXTURES = [
    'demo-training-type.json', 'demo-user.json',
    'site-data.json', 'demo-project.json',
]


def bound_form_data(form):
    """
    Return POST data reproducing the current values of an unbound form.
    """
    data = {}
    for name, field in form.fields.items():
        value = form[name].value()
        key = form.add_prefix(name)
        if value is None or value is False:
            continue
        if value is True:
            data[key] = 'on'
        elif isinstance(value, (list, tuple)):
            data[key] = [str(v) for v in value]
        else:
            data[key] = str(value)
    return data


def bound_formset_data(formset):
    data = {}
    management = formset.management_form
    for name in management.fields:
        data[management.add_prefix(name)] = management[name].value()
    for form in formset.forms:
        data.update(bound_form_data(form))
    return data


class TestFunderIdentifier(TestCase):
    def test_normalize_ror(self):
        for value in ('01cwqze88', 'ror.org/01cwqze88', 'https://ror.org/01cwqze88',
                      ' HTTPS://ROR.ORG/01CWQZE88 '):
            self.assertEqual(normalize_funder_identifier(value),
                             'https://ror.org/01cwqze88')

    def test_normalize_crossref(self):
        for value in ('10.13039/100000002', 'doi:10.13039/100000002',
                      'https://doi.org/10.13039/100000002',
                      'http://dx.doi.org/10.13039/100000002'):
            self.assertEqual(normalize_funder_identifier(value),
                             'https://doi.org/10.13039/100000002')

    def test_validate(self):
        validate_funder_identifier('https://ror.org/01cwqze88')
        validate_funder_identifier('https://doi.org/10.13039/100000002')
        for value in ('https://example.org/funder', 'https://ror.org/abc',
                      'https://doi.org/10.1000/123'):
            with self.assertRaises(ValidationError):
                validate_funder_identifier(value)


class TestFundingSubmission(TestCase):
    fixtures = FIXTURES

    AUTHOR = 'rgmark@mit.edu'
    PASSWORD = 'Tester11!'
    PROJECT_TITLE = 'MIT-BIH Arrhythmia Database'

    def setUp(self):
        self.project = ActiveProject.objects.get(title=self.PROJECT_TITLE)
        self.url = reverse('project_discovery', args=(self.project.slug,))
        self.client.login(username=self.AUTHOR, password=self.PASSWORD)

    def discovery_data(self, funding_rows=()):
        """
        POST data for the discovery page, with extra funding rows added.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        context = response.context
        data = bound_form_data(context['discovery_form'])
        data.update(bound_formset_data(context['publication_formset']))
        data.update(bound_formset_data(context['topic_formset']))
        funding_formset = context['funding_formset']
        data.update(bound_formset_data(funding_formset))

        prefix = funding_formset.prefix
        start = len(funding_formset.forms)
        for i, row in enumerate(funding_rows, start=start):
            for key, value in row.items():
                data[f'{prefix}-{i}-{key}'] = value
        data[f'{prefix}-TOTAL_FORMS'] = start + len(funding_rows)
        return data

    def test_funding_is_optional(self):
        self.assertFalse(self.project.funding.exists())
        self.assertTrue(self.project.check_integrity())
        response = self.client.get(reverse('project_preview', args=(self.project.slug,)))
        self.assertNotContains(response, 'id="funding"')

    def test_add_funding(self):
        data = self.discovery_data(funding_rows=[
            {'funder_name': '  National Natural Science   Foundation of China ',
             'funder_identifier': '01h0zpd94',
             'award_number': ' 31960558 '},
            {'funder_name': 'Natural Science Foundation of Jiangxi Province',
             'award_number': '20242BAB25204'},
        ])
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(response.context['funding_formset'].errors))

        self.project.refresh_from_db()
        funding = list(self.project.funding.all())
        self.assertEqual([str(f) for f in funding], [
            'National Natural Science Foundation of China: 31960558',
            'Natural Science Foundation of Jiangxi Province: 20242BAB25204',
        ])
        self.assertEqual(funding[0].funder_identifier, 'https://ror.org/01h0zpd94')
        self.assertEqual([f.order for f in funding], [0, 1])
        self.assertTrue(self.project.check_integrity())

        # Remove an entry through the AJAX item view
        response = self.client.post(
            reverse('edit_content_item', args=(self.project.slug,)),
            {'item': 'funding', 'remove_id': funding[1].id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.project.funding.count(), 1)

        # Add a blank first form through the AJAX item view
        Funding.objects.filter(object_id=self.project.id).delete()
        response = self.client.get(
            reverse('edit_content_item', args=(self.project.slug,)),
            {'item': 'funding', 'add_first': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Funder name')

    def test_invalid_funder_identifier(self):
        data = self.discovery_data(funding_rows=[
            {'funder_name': 'Wellcome Trust',
             'funder_identifier': 'https://example.org/wellcome'},
        ])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Enter a ROR ID')
        self.assertFalse(self.project.funding.exists())

    def test_duplicate_funding(self):
        row = {'funder_name': 'Wellcome Trust', 'award_number': '123'}
        data = self.discovery_data(funding_rows=[row, row])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'must be unique')
        self.assertFalse(self.project.funding.exists())

    def test_submission_snapshot_includes_funding(self):
        Funding.objects.create(project=self.project, funder_name='Wellcome Trust',
                               award_number='123')
        snapshot = self.project.submission_metadata_snapshot()
        self.assertEqual(snapshot['funding'][0]['funder_name'], 'Wellcome Trust')
        self.assertEqual(snapshot['funding'][0]['award_number'], '123')

    def test_preview_hides_funding(self):
        # Funding goes into the DataCite metadata but isn't shown on the page
        Funding.objects.create(project=self.project, funder_name='Wellcome Trust',
                               award_number='123')
        response = self.client.get(reverse('project_preview', args=(self.project.slug,)))
        self.assertNotContains(response, 'id="funding"')
        self.assertNotContains(response, 'Wellcome Trust')

    def test_cannot_remove_other_project_funding(self):
        other = ActiveProject.objects.get(title='Demo database project')
        funding = Funding.objects.create(project=other, funder_name='Wellcome Trust')
        response = self.client.post(
            reverse('edit_content_item', args=(self.project.slug,)),
            {'item': 'funding', 'remove_id': funding.id})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Funding.objects.filter(id=funding.id).exists())


class TestFundingMetadata(TestCase):
    fixtures = FIXTURES

    def setUp(self):
        # Demo eICU has one funding entry in the fixtures
        self.project = PublishedProject.objects.get(slug='demoeicu', version='2.0.0')

    def test_datacite_payload(self):
        payload = generate_doi_payload(self.project, event='publish')
        self.assertEqual(payload['data']['attributes']['fundingReferences'], [{
            'funderName': 'National Institutes of Health',
            'funderIdentifier': 'https://ror.org/01cwqze88',
            'funderIdentifierType': 'ROR',
            'awardNumber': 'R01-EB017205',
        }])

    def test_datacite_payload_crossref_without_award(self):
        self.project.funding.all().delete()
        self.project.funding.create(
            funder_name='National Science Foundation',
            funder_identifier='https://doi.org/10.13039/100000001')
        payload = generate_doi_payload(self.project, event='publish')
        self.assertEqual(payload['data']['attributes']['fundingReferences'], [{
            'funderName': 'National Science Foundation',
            'funderIdentifier': 'https://doi.org/10.13039/100000001',
            'funderIdentifierType': 'Crossref Funder ID',
        }])

    def test_datacite_payload_award_details(self):
        funding = self.project.funding.get()
        funding.award_title = 'Critical care research'
        funding.award_uri = 'https://reporter.nih.gov/project-details/R01EB017205'
        funding.save()
        payload = generate_doi_payload(self.project, event='publish')
        reference = payload['data']['attributes']['fundingReferences'][0]
        self.assertEqual(reference['awardTitle'], 'Critical care research')
        self.assertEqual(reference['awardUri'],
                         'https://reporter.nih.gov/project-details/R01EB017205')

    def test_published_page_and_schema_org(self):
        self.project.funding.create(
            funder_name='Fund </script> & Co', award_number='A1', order=1)
        response = self.client.get(reverse('published_project',
                                           args=(self.project.slug, self.project.version)))
        self.assertNotContains(response, 'id="funding"')

        content = response.content.decode()
        start = content.index('<script type="application/ld+json">') + len(
            '<script type="application/ld+json">')
        end = content.index('</script>', start)
        metadata = json.loads(content[start:end])
        self.assertEqual(metadata['funding'][0], {
            '@type': 'Grant',
            'identifier': 'R01-EB017205',
            'funder': {'@type': 'Organization', 'name': 'National Institutes of Health',
                       '@id': 'https://ror.org/01cwqze88'},
        })
        self.assertEqual(metadata['funding'][1]['funder']['name'], 'Fund </script> & Co')

    def test_schema_org_without_funding(self):
        self.project.funding.all().delete()
        response = self.client.get(reverse('published_project',
                                           args=(self.project.slug, self.project.version)))
        content = response.content.decode()
        start = content.index('<script type="application/ld+json">') + len(
            '<script type="application/ld+json">')
        end = content.index('</script>', start)
        self.assertNotIn('funding', json.loads(content[start:end]))
        self.assertNotIn('id="funding"', content)

    def test_api_detail(self):
        response = self.client.get(reverse('published_project_detail', kwargs={
            'project_slug': self.project.slug, 'version': self.project.version}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['funding'], [{
            'funder_name': 'National Institutes of Health',
            'funder_identifier': 'https://ror.org/01cwqze88',
            'funder_identifier_type': 'ROR',
            'award_number': 'R01-EB017205',
            'award_title': '',
            'award_uri': '',
        }])


class TestFundingCopyedit(TestMixin):
    fixtures = FIXTURES

    def test_editor_edits_funding(self):
        """
        The editor can add a funding source during copyedit.
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        project.assign_editor(User.objects.get(username='admin'))
        project.submission_status = SubmissionStatus.NEEDS_DECISION
        project.save()
        self.client.login(username='admin', password='Tester11!')
        self.client.post(reverse('edit_submission', args=(project.slug,)), data={
            'soundly_produced': 1, 'well_described': 1, 'open_format': 1,
            'data_machine_readable': 1, 'reusable': 1, 'no_phi': 1,
            'pn_suitable': 1, 'editor_comments': 'Good.', 'decision': 2,
            'ethics_included': 1,
        })
        project.refresh_from_db()
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_COPYEDIT)

        url = reverse('copyedit_submission', args=(project.slug,))
        response = self.client.get(url)
        self.assertContains(response, 'Funding')
        context = response.context
        data = {'edit_content': ''}
        for name in ('description_form', 'ethics_form', 'access_form', 'discovery_form'):
            data.update(bound_form_data(context[name]))
        for name in ('reference_formset', 'publication_formset', 'topic_formset'):
            data.update(bound_formset_data(context[name]))
        funding_formset = context['funding_formset']
        data.update(bound_formset_data(funding_formset))

        prefix = funding_formset.prefix
        data[f'{prefix}-TOTAL_FORMS'] = 1
        data[f'{prefix}-0-funder_name'] = 'Wellcome Trust'
        data[f'{prefix}-0-award_number'] = '123'
        response = self.client.post(url, data)
        self.assertContains(response, 'The project metadata has been updated.')
        self.assertEqual([str(f) for f in project.funding.all()], ['Wellcome Trust: 123'])
