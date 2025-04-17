from django.test import TestCase

from project.models import ProjectType


class TestProjectTypes(TestCase):
    def test_content_sections(self):
        for project_type in ProjectType.objects.all():
            headers = project_type.content_section_headers()
            self.assertGreater(len(headers), 0)

            # all project types should have a mandatory abstract field
            self.assertEqual(headers[0].html_id, 'abstract')
            self.assertEqual(headers[0].field_name, 'abstract')
            self.assertTrue(headers[0].required)

            # html_ids must be unique
            html_ids = [header.html_id for header in headers]
            self.assertEqual(len(headers), len(set(html_ids)))

            # field_names must be unique
            field_names = [header.field_name for header in headers]
            self.assertEqual(len(headers), len(set(field_names)))
