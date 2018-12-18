"""
Test functionality of publishing projects
"""
import logging
import os
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

    def test_submittable(self):
        """
        Make sure some projects are and others are not able to be
        submitted.
        """
        self.assertTrue(ActiveProject.objects.get(
            title='MIT-BIH Arrhythmia Database').is_submittable())
        self.assertFalse(ActiveProject.objects.get(
            title='MIMIC-III Clinical Database').is_submittable())


class SeleniumTests(StaticLiveServerTestCase):

    fixtures = ['demo-user', 'demo-project']
    cleanup_projects = []

    @classmethod
    def setUpClass(cls):
        super(SeleniumTests, cls).setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(3)


    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(SeleniumTests, cls).tearDownClass()

        # project = ActiveProject.objects.filter(title='Data Project 1').first()
        # if project:
        #     project.remove()

    def selenium_login(self, username, password, new=False):
        """
        Log in. If new, log out of old account first.
        """
        if new:
            self.selenium.find_element_by_id('account_dropdown').click()
            self.selenium.find_element_by_id('nav_logout').click()
        self.selenium.get('{}{}'.format(self.live_server_url, reverse('login')))
        self.selenium.find_element_by_name('username').send_keys(username)
        self.selenium.find_element_by_name("password").send_keys(password)
        self.selenium.find_element_by_id('login').click()

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

    def test_publish_project(self):
        self.selenium_login(username='rgmark', password='Tester11!')
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

        # Metadata
        self.selenium.find_element_by_id('metadata_tab').click()
        self.send_ck_content(outer_id='cke_id_background', content='Background')
        self.send_ck_content(outer_id='cke_id_methods', content='Methods')
        self.send_ck_content(outer_id='cke_id_content_description', content='Data Description')
        self.send_ck_content(outer_id='cke_id_usage_notes', content='Usage Notes')
        self.selenium.find_element_by_id('id_version').send_keys('1.0.0')
        self.send_ck_content(outer_id='cke_id_release_notes', content='Release Notes')
        self.send_ck_content(outer_id='cke_id_acknowledgements', content='Acknowledgements')
        self.send_ck_content(outer_id='cke_id_conflicts_of_interest', content='Conflicts of Interest')
        self.selenium.find_element_by_id('add-reference-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_project-reference-content_type-object_id-0-description')))
        element.send_keys('Reference 1')
        self.selenium.find_element_by_id('add-reference-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_project-reference-content_type-object_id-1-description')))
        self.selenium.find_element_by_name('edit_description').click()

        # Access
        self.selenium.find_element_by_id('access_tab').click()
        Select(self.selenium.find_element_by_name('license')).select_by_visible_text('Creative Commons Attribution 4.0 International Public License')
        self.selenium.find_element_by_name('edit_access').click()

        # Identifiers
        self.selenium.find_element_by_id('identifiers_tab').click()
        self.selenium.find_element_by_id('id_project_home_page').send_keys('https://physionet.org')
        self.selenium.find_element_by_id('add-publication-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_project-publication-content_type-object_id-0-citation')))
        element.send_keys('Citation')
        self.selenium.find_element_by_id('id_project-publication-content_type-object_id-0-url').send_keys('https://google.com')
        self.selenium.find_element_by_id('add-topic-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_project-topic-content_type-object_id-0-description')))
        element.send_keys('Topic 1')
        self.selenium.find_element_by_id('add-topic-button').click()
        element = WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'id_project-topic-content_type-object_id-1-description')))
        element.send_keys('Topic 2')
        self.selenium.find_element_by_name('edit_identifiers').click()

        # Files - Create 2 folders, rename one, delete one, navigate to one.
        self.selenium.find_element_by_id('files_tab').click()
        self.selenium.find_element_by_id('request-storage-button').click()
        self.selenium.find_element_by_id('id_request_allowance').send_keys(10)
        self.selenium.find_element_by_id('request-storage-button-submit').click()
        self.selenium.find_element_by_id('create-folder-button').click()
        self.selenium.find_element_by_id('id_folder_name').send_keys('subject-1')
        self.selenium.find_element_by_id('create-folder-button-submit').click()
        self.selenium.find_element_by_name('items').click()
        self.selenium.find_element_by_id('rename-item-button').click()
        self.selenium.find_element_by_id('id_new_name').send_keys('subject-10')
        self.selenium.find_element_by_id('rename-item-button-submit').click()
        self.selenium.find_element_by_id('create-folder-button').click()
        self.selenium.find_element_by_id('id_folder_name').send_keys('subject-2')
        self.selenium.find_element_by_id('create-folder-button-submit').click()
        # Instead of uploading files via form, just create some for now
        project = ActiveProject.objects.get(title='Data Project 1')
        with open(os.path.join(project.file_root(), 'subject-info.csv'), 'w') as f:
            f.write('number,age,gender\n10,50,F')
        with open(os.path.join(project.file_root(), 'subject-10', '10.txt'), 'w') as f:
            f.write('subject 10 from hospital')

        # Proofread/preview
        self.selenium.find_element_by_id('proofread_tab').click()
        self.selenium.find_element_by_id('view_preview').click()
        self.selenium.switch_to.window(self.selenium.window_handles[0])

        # Accept author invitation as second user
        self.selenium_login(username='aewj', password='Tester11!', new=True)
        self.selenium.find_element_by_id('respond_button_{}'.format(project.id)).click()
        self.selenium.find_element_by_name('invitation_response').click()

        # Approve storage request as admin
        self.selenium_login(username='admin', password='Tester11!', new=True)
        self.selenium.find_element_by_id('account_dropdown').click()
        self.selenium.find_element_by_id('nav_admin').click()
        self.selenium.find_element_by_id('nav_storage_requests').click()
        self.selenium.find_element_by_id('respond_button_{}'.format(project.id)).click()
        self.selenium.find_element_by_name('storage_response').click()

        self.selenium_login(username='rgmark', password='Tester11!', new=True)

        pdb.set_trace()

