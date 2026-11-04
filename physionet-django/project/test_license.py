from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.forms.models import model_to_dict
from django.test import TestCase, override_settings
from django.utils import timezone

from console.forms import LicenseForm
from physionet.settings.base import StorageTypes
from project.license_content import license_html_to_text
from project.models import ActiveProject, License, ProjectType


LONG_COPYRIGHT_HTML = (
    '<p>' + 'x' * 50 + ' Copyright &lt;YEAR&gt; &lt;COPYRIGHT HOLDER&gt; more words</p>'
)


class LicenseTextTests(TestCase):
    def create_license(self, **kwargs):
        values = dict(
            name='Test license', slug='test-license', version='1.0',
            html_content='<p>Copyright &lt;YEAR&gt; &lt;COPYRIGHT HOLDER&gt;</p>',
            home_page='https://example.com/',
        )
        values.update(kwargs)
        return License.objects.create(**values)

    def form_data(self, license):
        project_type, _ = ProjectType.objects.get_or_create(
            pk=0, defaults={'name': 'Database', 'description': 'Database'},
        )
        license.project_types.add(project_type)
        return model_to_dict(license)

    def test_save_generates_text_and_preserves_placeholders(self):
        license = self.create_license()
        license.refresh_from_db()
        self.assertEqual(license.text_content.strip(), 'Copyright <YEAR> <COPYRIGHT HOLDER>')

    def test_html_update_regenerates_text(self):
        license = self.create_license()
        license.html_content = '<p>Updated license</p>'
        license.save(update_fields=['html_content'])
        license.refresh_from_db()
        self.assertEqual(license.text_content.strip(), 'Updated license')

    def test_conversion_preserves_long_copyright_placeholder(self):
        license = self.create_license(html_content=LONG_COPYRIGHT_HTML)
        license.refresh_from_db()
        self.assertIn('<COPYRIGHT HOLDER>', license.text_content)
        self.assertIn('<YEAR>', license.text_content)

    def test_conversion_removes_emphasis_and_preserves_link_destination(self):
        text = license_html_to_text(
            '<p><strong>MIT License</strong> <em>Terms</em> '
            '<a href="https://example.com/terms">Full terms</a></p>',
        )
        self.assertIn('MIT License Terms', text)
        self.assertNotIn('*', text)
        self.assertIn('Full terms', text)
        self.assertIn('https://example.com/terms', text)

    def test_empty_html_clears_text(self):
        license = self.create_license()
        license.html_content = ''
        license.save()
        license.refresh_from_db()
        self.assertEqual(license.text_content.strip(), '')

    def test_unrelated_update_preserves_existing_text(self):
        license = self.create_license()
        License.objects.filter(pk=license.pk).update(text_content='Existing text')
        license.is_active = False
        license.save(update_fields=['is_active'])
        license.refresh_from_db()
        self.assertEqual(license.text_content, 'Existing text')

    def test_console_new_version_generates_text(self):
        license = self.create_license()
        data = self.form_data(license)
        data.update(slug='test-license-v2', version='2.0')
        form = LicenseForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        new_license = form.save()
        new_license.refresh_from_db()
        self.assertEqual(new_license.text_content, license.text_content)

    def test_console_edit_regenerates_text_on_full_save(self):
        license = self.create_license(html_content='<p><strong>License terms</strong></p>')
        License.objects.filter(pk=license.pk).update(text_content='Hand-formatted text')
        license.refresh_from_db()
        data = self.form_data(license)
        data['is_active'] = False
        form = LicenseForm(data=data, instance=license)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        license.refresh_from_db()
        self.assertFalse(license.is_active)
        self.assertEqual(license.text_content.strip(), 'License terms')

    def test_backfill_only_changes_empty_text(self):
        license = self.create_license(html_content=LONG_COPYRIGHT_HTML)
        preserved = self.create_license_for_backfill()
        License.objects.filter(pk=license.pk).update(text_content='')
        migration = import_module('project.migrations.0111_fill_license_text_content')
        migration.fill_license_text_content(apps, SimpleNamespace(connection=connection))
        license.refresh_from_db()
        preserved.refresh_from_db()
        self.assertEqual(license.text_content, license_html_to_text(license.html_content))
        self.assertIn('Copyright <YEAR> <COPYRIGHT HOLDER>', license.text_content)
        self.assertEqual(preserved.text_content, 'Existing text')

    def create_license_for_backfill(self):
        license = License.objects.create(
            name='Existing license', slug='existing-license', html_content='<p>Existing</p>',
        )
        License.objects.filter(pk=license.pk).update(text_content='Existing text')
        return license


@override_settings(STORAGE_TYPE=StorageTypes.LOCAL)
class LicenseFileTests(TestCase):
    fixtures = [
        'demo-training-type.json', 'demo-user.json', 'site-data.json', 'demo-project.json',
    ]

    def test_license_file_replaces_long_copyright_placeholders(self):
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.license = License.objects.create(
            name='Test license', slug='test-license', html_content=LONG_COPYRIGHT_HTML,
        )
        author_names = ', '.join(
            author.get_full_name() for author in project.authors.order_by('display_order')
        ) + '.'
        self.assertNotEqual(author_names, '.')
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            root = Path(project.file_root())
            root.mkdir(parents=True)
            project.create_license_file()
            content = (root / 'LICENSE.txt').read_text()

        self.assertIn(f'Copyright {timezone.now().year} {author_names} more words', content)
        self.assertNotIn('<YEAR>', content)
        self.assertNotIn('<COPYRIGHT', content)
