"""
Test functionality of publishing projects
"""
import logging
import pdb

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.test import TestCase
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from project.models import ActiveProject
from user.models import User


def prevent_request_warnings(original_function):
    """
    If we need to test for 404s or 405s this decorator can prevent the
    request class from throwing warnings.
    """
    def new_function(*args, **kwargs):
        # raise logging level to ERROR
        logger = logging.getLogger('django.request')
        previous_logging_level = logger.getEffectiveLevel()
        logger.setLevel(logging.ERROR)
        # trigger original function that would throw warning
        original_function(*args, **kwargs)
        # lower logging level back to previous
        logger.setLevel(previous_logging_level)

    return new_function


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

    @prevent_request_warnings
    def test_navigate_project(self):
        """
        Create a project and visit all views of it
        """
        response = self.client.post(reverse('create_project'),
            data={'title':'Database 1', 'resource_type':0})
        project = ActiveProject.objects.get(title='Database 1')
        self.assertRedirects(response, reverse('project_overview', args=(project.slug,)))

        # Visit all the views of the new project
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)

        # Try again with a non-author who cannot access
        self.client.login(username='george@mit.edu', password='Tester11!')
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


    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(SeleniumTests, cls).tearDownClass()

    def send_ck_content(self, outer_id, content):
        """
        Helper function to send content to a ckeditor richtextfield
        """
        # Get the frame, then send content to the body
        frame = self.selenium.find_element_by_id(outer_id).find_element_by_class_name('cke_inner').find_element_by_class_name('cke_contents').find_element_by_class_name('cke_wysiwyg_frame')
        self.selenium.switch_to.frame(frame)
        editor_body = self.selenium.find_element_by_tag_name('body')
        editor_body.send_keys(content)
        self.selenium.switch_to.default_content()


    def test_navigate_project(self):
        # Login
        self.selenium.get('{}{}'.format(self.live_server_url, reverse('login')))
        self.selenium.find_element_by_name('username').send_keys('rgmark')
        self.selenium.find_element_by_name("password").send_keys('Tester11!')
        self.selenium.find_element_by_id('login').click()

        # Create project
        self.selenium.find_element_by_id('create_project').click()
        Select(self.selenium.find_element_by_name('resource_type')).select_by_visible_text('Database')
        self.selenium.find_element_by_name('title').send_keys('Data Project 1')
        self.send_ck_content(outer_id='cke_id_abstract', content='A large database')
        self.selenium.find_element_by_id('create_project').click()

        # Author info - invite author and add 2 affiliations
        self.selenium.find_element_by_id('authors_tab').click()
        self.selenium.find_element_by_id('id_email').send_keys('aewj@mit.edu')
        self.selenium.find_element_by_name('invite_author').click()
        self.selenium.find_element_by_id('add-affiliation-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_affiliations-1-name')))
        element.send_keys('Harvard University')
        self.selenium.find_element_by_id('add-affiliation-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_affiliations-2-name')))
        element.send_keys('Beth Israel Deaconess Medical Center')
        self.selenium.find_element_by_name('edit_affiliations').click()
        #
        pdb.set_trace()

