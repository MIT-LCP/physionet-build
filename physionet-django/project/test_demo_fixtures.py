import json
import os

from django.conf import settings
from django.test import SimpleTestCase


class TestDemoPublishedProjects(SimpleTestCase):
    """
    Check that the demo published project files and the PublishedProject
    objects in demo-project.json are kept in sync.
    """

    def test_demo_files_match_fixture(self):
        fixture = os.path.join(settings.BASE_DIR, 'project', 'fixtures', 'demo-project.json')
        with open(fixture) as f:
            fixture_projects = {
                (obj['fields']['slug'], obj['fields']['version'])
                for obj in json.load(f)
                if obj['model'] == 'project.publishedproject'
            }

        files_root = os.path.join(settings.DEMO_FILE_ROOT, 'media', 'published-projects')
        file_projects = {
            (slug, version)
            for slug in os.listdir(files_root)
            if os.path.isdir(os.path.join(files_root, slug))
            for version in os.listdir(os.path.join(files_root, slug))
            if os.path.isdir(os.path.join(files_root, slug, version))
        }

        self.assertEqual(
            file_projects - fixture_projects, set(),
            'Demo project files have no PublishedProject in demo-project.json',
        )
        self.assertEqual(
            fixture_projects - file_projects, set(),
            'PublishedProjects in demo-project.json have no demo project files',
        )
