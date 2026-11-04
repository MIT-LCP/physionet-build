from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

from django.apps import apps
from django.db import connection
from django.forms.models import model_to_dict
from django.test import TestCase

from console.forms import LicenseForm
from project.models import License, ProjectType
from project.modelcomponents.metadata import Metadata


class LicenseTextTests(TestCase):
    def create_license(self, **kwargs):
        return License.objects.create(
            name='Test license', slug='test-license',
            html_content='<p>Copyright &lt;YEAR&gt; &lt;COPYRIGHT HOLDER&gt;</p>',
            **kwargs,
        )

    def test_save_generates_text_and_preserves_placeholders(self):
        license = self.create_license()
        license.refresh_from_db()
        self.assertEqual(license.text_content, 'Copyright <YEAR> <COPYRIGHT HOLDER>\n\n')

    def test_html_update_regenerates_text(self):
        license = self.create_license()
        license.html_content = '<p>Updated license</p>'
        license.save(update_fields=['html_content'])
        license.refresh_from_db()
        self.assertEqual(license.text_content, 'Updated license\n\n')

    def test_license_file_contains_generated_text(self):
        license = self.create_license()
        project = Mock(license=license)
        project.authors.all.return_value.order_by.return_value = [
            Mock(get_full_name=Mock(return_value='Test Author')),
        ]
        project.file_root.return_value = '/project'
        project.license_content.side_effect = lambda fmt: Metadata.license_content(project, fmt)
        Metadata.create_license_file(project)
        path, content = project.files.fwrite.call_args.args
        self.assertEqual(path, '/project/LICENSE.txt')
        self.assertIn('Test Author', content)
        self.assertNotIn('<YEAR>', content)
        self.assertNotIn('<COPYRIGHT HOLDER>', content)

    def test_unrelated_update_preserves_existing_text(self):
        license = self.create_license()
        License.objects.filter(pk=license.pk).update(text_content='Existing text')
        license.is_active = False
        license.save(update_fields=['is_active'])
        license.refresh_from_db()
        self.assertEqual(license.text_content, 'Existing text')

    def test_console_new_version_generates_text(self):
        license = self.create_license(home_page='https://example.com/')
        project_type = ProjectType.objects.first()
        self.assertIsNotNone(project_type)
        license.project_types.add(project_type)
        data = model_to_dict(license)
        data.update(slug='test-license-v2', version='2.0')
        form = LicenseForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        new_license = form.save()
        new_license.refresh_from_db()
        self.assertEqual(new_license.text_content, license.text_content)

    def test_backfill_only_changes_empty_text(self):
        license = self.create_license()
        preserved = self.create_license_for_backfill()
        License.objects.filter(pk=license.pk).update(text_content='')
        migration = import_module('project.migrations.0111_fill_license_text_content')
        migration.fill_license_text_content(apps, SimpleNamespace(connection=connection))
        license.refresh_from_db()
        preserved.refresh_from_db()
        self.assertIn('Copyright <YEAR> <COPYRIGHT HOLDER>', license.text_content)
        self.assertEqual(preserved.text_content, 'Existing text')

    def create_license_for_backfill(self):
        license = License.objects.create(
            name='Existing license', slug='existing-license', html_content='<p>Existing</p>',
        )
        License.objects.filter(pk=license.pk).update(text_content='Existing text')
        return license
