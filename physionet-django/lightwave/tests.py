import json
import shutil
from unittest import skipIf

from django.urls import reverse

from project.models import ActiveProject
from user.test_views import prevent_request_warnings, TestMixin


test_queries = (
    'action=dblist',
    'action=rlist&db={db}',
    'action=alist&db={db}',
    'action=info&db={db}&record={record}',
)

server = shutil.which('sandboxed-lightwave')


class TestPublished(TestMixin):
    """
    Test operation of LightWAVE server for public databases.
    """

    def test_home(self):
        response = self.client.get(reverse('lightwave_home'))
        self.assertEqual(response.status_code, 200)

    @skipIf(server is None, "sandboxed-lightwave is not installed")
    def test_server(self):
        server = reverse('lightwave_server')
        for q in test_queries:
            qstr = q.format(db='demobsn/1.0', record='231')

            response = self.client.get(server + '?' + qstr)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content.decode())
            self.assertEqual(data['success'], True)

            response = self.client.get(server + '?' + qstr + '&callback=X')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content.decode()[2:-1])
            self.assertEqual(data['success'], True)


class TestUnpublished(TestMixin):
    """
    Test operation of LightWAVE server for active projects.
    """

    @prevent_request_warnings
    def test_home(self):
        project = ActiveProject.objects.get(
            title='MIT-BIH Arrhythmia Database')

        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.get(reverse('lightwave_project_home',
                                           args=(project.slug,)))
        self.assertEqual(response.status_code, 200)

        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.get(reverse('lightwave_project_home',
                                           args=(project.slug,)))
        self.assertEqual(response.status_code, 403)

    @skipIf(server is None, "sandboxed-lightwave is not installed")
    @prevent_request_warnings
    def test_server(self):
        project = ActiveProject.objects.get(
            title='MIT-BIH Arrhythmia Database')
        server = reverse('lightwave_project_server', args=(project.slug,))

        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        for q in test_queries:
            qstr = q.format(db=project.slug, record='subject-102/102')

            response = self.client.get(server + '?' + qstr)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content.decode())
            self.assertEqual(data['success'], True)

        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.get(server + '?action=dblist')
        self.assertEqual(response.status_code, 403)
