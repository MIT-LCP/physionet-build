from django.test import TestCase
from django.urls import reverse

from project.models import ActiveProject, PublishedProject, Reference
from project.reference_citations import (
    citation_numbers,
    citation_problems,
    find_cited_keys,
    find_citations,
    key_numbered_citations,
    link_citations,
    number_key_citations,
    order_references,
    suggest_key,
)
from project.test_funding import FIXTURES, bound_form_data, bound_formset_data


def link(number, title):
    return f'<a href="#ref-{number}" class="citation-link" title="{title}">{number}</a>'


class Ref:
    """
    A stand-in for a reference: a key and a citation.
    """
    def __init__(self, key, description=None):
        self.key = key
        self.description = description or key

    def __str__(self):
        return self.description


class TestCitationNumbers(TestCase):
    def test_numbers(self):
        self.assertEqual(citation_numbers('[1]'), [1])
        self.assertEqual(citation_numbers('[ 2, 3 ]'), [2, 3])
        self.assertEqual(citation_numbers('[1, 4-6]'), [1, 4, 5, 6])
        self.assertEqual(citation_numbers('[2–4]'), [2, 3, 4])

    def test_not_citations(self):
        self.assertIsNone(citation_numbers('[5-2]'))
        self.assertIsNone(citation_numbers('[1-500]'))


class TestFindCitations(TestCase):
    def test_find(self):
        self.assertEqual(find_citations('<p>See [1] and [2, 4-5].</p><p>Also [3]</p>'), {1, 2, 3, 4, 5})

    def test_ignored(self):
        document = (
            '<p>x[1], f(2)[2], [0], [2019], [a], [1.5]</p>'
            '<p><a href="/x">[3]</a> <code>y = z [4]</code></p>'
            '<pre>[5]</pre><math><mi>v</mi><mo>[</mo><mn>6</mn><mo>]</mo></math>'
            '<!-- [7] -->'
        )
        self.assertEqual(find_citations(document), set())

    def test_empty(self):
        self.assertEqual(find_citations(''), set())
        self.assertEqual(find_citations(None), set())


class TestLinkCitations(TestCase):
    REFERENCES = [Ref('', 'Moody & Mark (2001). "The paper".'), Ref('', 'Second (2002).'),
                  Ref('', 'Third (2003).')]

    def test_link(self):
        a1 = link(1, 'Moody &amp; Mark (2001). &quot;The paper&quot;.')
        a2 = link(2, 'Second (2002).')
        a3 = link(3, 'Third (2003).')
        self.assertEqual(
            link_citations('<p>As shown [1], [2, 3] and [1–3].</p>', self.REFERENCES),
            f'<p>As shown [{a1}], [{a2}, {a3}] and [{a1}–{a3}].</p>')

    def test_entity_dash(self):
        # The editor may save an en dash as an HTML entity
        a1 = link(1, 'Moody &amp; Mark (2001). &quot;The paper&quot;.')
        a3 = link(3, 'Third (2003).')
        for dash in ('&ndash;', '&#8211;', '&#x2013;'):
            self.assertEqual(link_citations('<p>[1' + dash + '3] &amp;</p>', self.REFERENCES),
                             '<p>[' + a1 + dash + a3 + '] &amp;</p>')
            self.assertEqual(find_citations('<p>[1' + dash + '3]</p>'), {1, 2, 3})

    def test_numbers_not_in_list(self):
        self.assertEqual(link_citations('<p>[4] and [2, 9]</p>', self.REFERENCES),
                         f'<p>[4] and [{link(2, "Second (2002).")}, 9]</p>')

    def test_rest_of_document_unchanged(self):
        document = ('<p class="x">A &amp; B &#65; &nbsp;<br>x[1] <a href="/a">[1]</a>'
                    '<code>[1]</code><img src="/i.png" alt="[1]"/></p><!-- [1] -->')
        self.assertEqual(link_citations(document, self.REFERENCES), document)

    def test_no_references(self):
        self.assertEqual(link_citations('<p>[1]</p>', []), '<p>[1]</p>')


class TestKeyCitations(TestCase):
    REFERENCES = [Ref('moody2001', 'Moody (2001).'), Ref('mark1997', 'Mark (1997).'),
                  Ref('goldberger2000', 'Goldberger (2000).'), Ref('extra2020', 'Extra (2020).')]
    DOCUMENT = ('<p>First [@goldberger2000], then [@Moody2001; @mark1997, @goldberger2000]. '
                'Not a@b.com or <code>[@extra2020]</code>, and [@unknown].</p>')

    def test_find_cited_keys(self):
        self.assertEqual(find_cited_keys(self.DOCUMENT), ['goldberger2000', 'moody2001', 'mark1997', 'unknown'])
        self.assertEqual(find_cited_keys('<p>[@a.b-c:d_e] [@x.] @y [@ z]</p>'), ['a.b-c:d_e'])
        self.assertEqual(find_cited_keys(None), [])

    def test_order_references(self):
        ordered = order_references([self.DOCUMENT], self.REFERENCES)
        self.assertEqual([r.key for r in ordered], ['goldberger2000', 'moody2001', 'mark1997', 'extra2020'])
        # Uncited references keep their order
        self.assertEqual(order_references(['<p>None</p>'], self.REFERENCES), self.REFERENCES)

    def test_number_key_citations(self):
        ordered = order_references([self.DOCUMENT], self.REFERENCES)
        self.assertEqual(
            number_key_citations(self.DOCUMENT, ordered),
            '<p>First [1], then [1–3]. Not a@b.com or <code>[@extra2020]</code>, and [@unknown].</p>')
        self.assertEqual(number_key_citations('<p>[@moody2001; @goldberger2000]</p>', self.REFERENCES),
                         '<p>[1, 3]</p>')

    def test_link_key_citations(self):
        self.assertEqual(
            link_citations('<p>[@mark1997; @moody2001]</p>', self.REFERENCES),
            '<p>[' + link(1, 'Moody (2001).') + ', ' + link(2, 'Mark (1997).') + ']</p>')

    def test_key_numbered_citations(self):
        self.assertEqual(
            key_numbered_citations('<p>[1, 3] [2–4] [1, 1] [9] x[1]</p>', self.REFERENCES),
            '<p>[@moody2001; @goldberger2000] [@mark1997; @goldberger2000; @extra2020] '
            '[@moody2001] [9] x[1]</p>')
        # References without keys are not cited by key
        self.assertEqual(key_numbered_citations('<p>[1]</p>', [Ref('')]), '<p>[1]</p>')

    def test_round_trip(self):
        ordered = order_references([self.DOCUMENT], self.REFERENCES)
        published = number_key_citations('<p>[@mark1997] and [@extra2020; @moody2001]</p>', ordered)
        self.assertEqual(published, '<p>[3] and [2, 4]</p>')
        self.assertEqual(key_numbered_citations(published, ordered),
                         '<p>[@mark1997] and [@moody2001; @extra2020]</p>')


class TestCitationProblems(TestCase):
    REFERENCES = [Ref('moody2001'), Ref('mark1997'), Ref('goldberger2000')]

    def test_all_cited(self):
        self.assertEqual(citation_problems(
            ['<p>[@moody2001]</p>', None, '<p>[@mark1997; @goldberger2000]</p>'], self.REFERENCES), ([], []))

    def test_unknown_keys(self):
        self.assertEqual(citation_problems(['<p>[@moody2001; @mark1997; @goldberger2000] [@nope]</p>'],
                                           self.REFERENCES),
                         (['The description cites @nope, but no reference has that key.'], []))
        errors, _ = citation_problems(['<p>[@a] [@b]</p>'], [])
        self.assertEqual(errors, ['The description cites @a and @b, but no references have those keys.'])

    def test_uncited(self):
        self.assertEqual(citation_problems(['<p>[@mark1997]</p>'], self.REFERENCES)[1],
                         ['References @moody2001 and @goldberger2000 are not cited in the description.'])
        self.assertEqual(citation_problems(['<p>[@mark1997; @moody2001]</p>'], self.REFERENCES)[1],
                         ['Reference @goldberger2000 is not cited in the description.'])
        self.assertEqual(citation_problems(['<p>No citations.</p>'], self.REFERENCES)[1], [
            'The references are not cited in the description. Cite them by key, for example [@moody2001].'])

    def test_numbered_citations(self):
        self.assertEqual(citation_problems(['<p>[1]</p>'], self.REFERENCES)[1], [
            'The description uses numbered citations such as [1]. Cite references by key instead, '
            'for example [@moody2001].'])

    def test_no_references_or_citations(self):
        self.assertEqual(citation_problems(['<p>Text.</p>'], []), ([], []))


class TestSuggestKey(TestCase):
    def test_suggest(self):
        for description, key in [
            ('Moody, G. B., & Mark, R. G. (2001). The impact.', 'moody2001'),
            ('van der Berg, J. (2019a). Title.', 'vanderberg2019a'),
            ('Ølsen, K., & Müller, A. (2010). Title.', 'olsen2010'),
            ('PhysioNet. (n.d.). WFDB.', 'physionetnd'),
            ('https://physionet.org/content/mitdb/', 'ref'),
            ('', 'ref'),
        ]:
            self.assertEqual(suggest_key(description), key)

    def test_taken(self):
        description = 'Moody, G. B. (2001). The impact.'
        self.assertEqual(suggest_key(description, ['MOODY2001']), 'moody2001b')
        self.assertEqual(suggest_key(description, ['moody2001', 'moody2001b']), 'moody2001c')


class TestReferenceKeys(TestCase):
    fixtures = FIXTURES

    def setUp(self):
        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.url = reverse('project_content', args=(self.project.slug,))
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

    def content_data(self, reference_rows=()):
        response = self.client.get(self.url)
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

    def test_keys_generated(self):
        data = self.content_data(reference_rows=[
            {'description': 'Moody, G. B., & Mark, R. G. (2001). The impact.', 'key': ''},
            {'description': 'Moody, G. B. (2001). Another paper.', 'key': ''},
            {'description': 'Mark, R. G. (1997). Directory.', 'key': ' [@Mark-dir] '},
        ])
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Your project content has been updated.')
        self.assertEqual(list(self.project.references.order_by('order').values_list('key', flat=True)),
                         ['moody2001', 'moody2001b', 'Mark-dir'])

    def test_existing_reference_given_key(self):
        reference = Reference.objects.create(project=self.project, order=1,
                                             description='Goldberger, A. L. (2000). PhysioNet.')
        response = self.client.post(self.url, self.content_data())
        self.assertContains(response, 'Your project content has been updated.')
        reference.refresh_from_db()
        self.assertEqual(reference.key, 'goldberger2000')

    def test_invalid_and_duplicate_keys(self):
        response = self.client.post(self.url, self.content_data(reference_rows=[
            {'description': 'A (2001).', 'key': 'bad key!'}]))
        self.assertContains(response, 'A key may contain letters, digits')
        response = self.client.post(self.url, self.content_data(reference_rows=[
            {'description': 'A (2001).', 'key': 'same'}, {'description': 'B (2002).', 'key': 'SAME'}]))
        self.assertContains(response, 'Each key may only be used for one reference: same')
        self.assertFalse(self.project.references.exists())

    def set_description(self, background):
        """
        Set the project's description, with no citations except in the
        background.
        """
        fields = {section.field_name: '<p>Text.</p>' for section in self.project.content_sections()}
        fields['background'] = background
        ActiveProject.objects.filter(pk=self.project.pk).update(**fields)
        self.project.refresh_from_db()

    def test_preview_and_integrity(self):
        self.set_description(
            '<p>Reviewed [@goldberger2000], first described [@moody2001; @goldberger2000].</p>')
        Reference.objects.create(project=self.project, order=1, key='moody2001', description='Moody (2001).')
        Reference.objects.create(project=self.project, order=2, key='mark1997', description='Mark (1997).')
        Reference.objects.create(project=self.project, order=3, key='goldberger2000',
                                 description='Goldberger (2000).')
        self.project.refresh_from_db()

        response = self.client.get(reverse('project_preview', args=(self.project.slug,)))
        self.assertContains(response, 'Reviewed [' + link(1, 'Goldberger (2000).') + ']', html=False)
        self.assertContains(response, 'described [' + link(1, 'Goldberger (2000).') + ', '
                            + link(2, 'Moody (2001).') + ']', html=False)
        # The list is in the order of first citation
        self.assertContains(response, '<li id="ref-1">Goldberger (2000).</li>', html=False)
        self.assertContains(response, '<li id="ref-3">Mark (1997).</li>', html=False)

        self.assertTrue(self.project.check_integrity())
        self.assertIn('Reference @mark1997 is not cited in the description.', self.project.integrity_warnings)

        # A key that no reference has prevents submission
        self.set_description('<p>[@moody2001; @mark1997; @goldberger2000] [@typo]</p>')
        self.assertFalse(self.project.check_integrity())
        self.assertIn('The description cites @typo, but no reference has that key.',
                      self.project.integrity_errors)


class TestPublishedCitations(TestCase):
    fixtures = FIXTURES

    def test_published_page(self):
        project = PublishedProject.objects.get(slug='demoeicu', version='2.0.0')
        references = list(project.ordered_references())
        PublishedProject.objects.filter(pk=project.pk).update(background='<p>See the tables [1].</p>')
        response = self.client.get(reverse('published_project', args=(project.slug, project.version)))
        self.assertContains(response, '[' + link(1, references[0].description) + ']', html=False)
        self.assertContains(response, '<li id="ref-1">', html=False)
