import pdb

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.test import TestCase
from selenium.webdriver.firefox.webdriver import WebDriver

from project.models import ActiveProject
from user.models import User


PROJECT_VIEWS = [
    'project_overview', 'project_authors', 'project_metadata',
    'project_access', 'project_identifiers', 'project_files',
    'project_proofread', 'project_preview', 'project_submission'
]

class TestCreate(TestCase):
    """
    Test creation
    """
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

    def test_navigate_project(self):
        """
        Create a project and visit all views of it
        """
        response = self.client.post(reverse('create_project'),
            data={'title':'Database 1', 'resource_type':0})
        project = ActiveProject.objects.get(title='Database 1')
        self.assertRedirects(response, reverse('project_overview', args=(project.slug,)))

        # Visit all the views
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)

        self.client.login(username='george@mit.edu', password='Tester11!')

        # Non authors cannot access
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 404)


class SeleniumTests(StaticLiveServerTestCase):

    fixtures = ['demo-user', 'demo-project']

    @classmethod
    def setUpClass(cls):
        super(SeleniumTests, cls).setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(1)
        cls.selenium.get('{}{}'.format(cls.live_server_url, reverse('login')))
        cls.selenium.find_element_by_name('username').send_keys('rgmark')
        cls.selenium.find_element_by_name("password").send_keys('Tester11!')
        cls.selenium.find_element_by_xpath("//button[contains(text(),'Log In')]").click()

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(SeleniumTests, cls).tearDownClass()

    def test_navigate_project(self):
        pass
