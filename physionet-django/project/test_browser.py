"""
Module with full browser tests.

"""
import time
import os
import pdb
import shutil

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.conf import settings
from django.urls import reverse
from django.test import tag, TestCase
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from user.test_views import TestMixin
from project.models import ActiveProject, PublishedProject, StorageRequest
from user.models import User


class BaseSeleniumTest(StaticLiveServerTestCase, TestCase):
    """
    Class to inherit for all selenium test classes. This inherits also
    from TestCase for its functionality in rolling back the database
    after each test. LiveServerTestCase only inherits from
    TransactionTestCase and produces errors when multiple tests are
    included in the same module. From the docs:

    https://docs.djangoproject.com/en/1.11/topics/testing/tools/#transactiontestcase

    - A TransactionTestCase resets the database after the test runs by
      truncating all tables. A TransactionTestCase may call commit and
      rollback and observe the effects of these calls on the database.
    - A TestCase, on the other hand, does not truncate tables after a
      test. Instead, it encloses the test code in a database transaction
      that is rolled back at the end of the test. This guarantees that
      the rollback at the end of the test restores the database to its
      initial state.

    """
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        options = Options()
        options.set_headless(True)
        cls.selenium = WebDriver(options=options)
        cls.selenium.implicitly_wait(10)

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super().tearDownClass()

    def setUp(self):
        """
        Copy the staticfiles dirs items into the testing effective
        static root. Emulates collectstatic, which cannot be used because
        the target directory may not actually be the static root,
        but the staticfiles_dirs[0] for the dev environment.

        This must be called after setUp of TestMixin which already
        creates the test effective static root.

        """
        # There is actual static root. Non-dev environment.
        if settings.STATIC_ROOT:
            test_static_root = settings.STATIC_ROOT
            staticfiles_dir = settings.STATICFILES_DIRS[0]
        # Because STATICFILES_DIRS[0] is modified in settings, point to real
        # location of static content.
        else:
            test_static_root = settings.STATICFILES_DIRS[0]
            staticfiles_dir = os.path.abspath(os.path.join(test_static_root, os.pardir))

        # Avoid recursive copy, and the created published projects
        for item in [s for s in os.listdir(staticfiles_dir) if s not in ['published-projects', 'test']]:
            full_item = os.path.join(staticfiles_dir, item)
            if os.path.isfile(full_item):
                shutil.copyfile(full_item, os.path.join(test_static_root, item))
            else:
                shutil.copytree(full_item,
                    os.path.join(test_static_root, item))

    def selenium_login(self, username, password, new=False):
        """
        Log in. If new, log out of old account first.
        """
        if new:
            # Wait for the navbar to be clickable
            element = WebDriverWait(self.selenium, 30).until(
                EC.element_to_be_clickable((By.ID, 'nav_account_dropdown')))
            time.sleep(1)
            element.click()
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


@tag('browser')
class TestSubmit(TestMixin, BaseSeleniumTest):
    def setUp(self):
        """
        Call methods in explicit order so that content is not
        overwritten. Both create testing static content.
        """
        TestMixin.setUp(self)
        BaseSeleniumTest.setUp(self)

    def Test_Submit(self):
        """
        Test steps to create and submit a project

        """
        pass
        # self.selenium_login(username='rgmark', password='Tester11!')
        # # Create project
        # self.selenium.find_element_by_id('create_project').click()
        # Select(self.selenium.find_element_by_name('resource_type')).select_by_visible_text('Database')
        # self.selenium.find_element_by_name('title').send_keys('Data Project 1')
        # self.send_ck_content(outer_id='cke_id_abstract', content='A large database')
        # self.selenium.find_element_by_id('create_project').click()

        # # Author info - invite author and add 2 affiliations
        # self.selenium.find_element_by_id('authors_tab').click()
        # self.selenium.find_element_by_id('id_email').send_keys('aewj@mit.edu')
        # self.selenium.find_element_by_name('invite_author').click()
        # self.selenium.find_element_by_id('add-affiliation-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_affiliations-1-name')))
        # element.send_keys('Harvard University')
        # self.selenium.find_element_by_id('add-affiliation-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_affiliations-2-name')))
        # element.send_keys('Beth Israel Deaconess Medical Center')
        # self.selenium.find_element_by_name('edit_affiliations').click()

        # # Content
        # self.selenium.find_element_by_id('content_tab').click()
        # self.send_ck_content(outer_id='cke_id_background', content='Background')
        # self.send_ck_content(outer_id='cke_id_methods', content='Methods')
        # self.send_ck_content(outer_id='cke_id_content_description', content='Data Description')
        # self.send_ck_content(outer_id='cke_id_usage_notes', content='Usage Notes')
        # self.selenium.find_element_by_id('id_version').send_keys('1.0.0')
        # self.send_ck_content(outer_id='cke_id_release_notes', content='Release Notes')
        # self.send_ck_content(outer_id='cke_id_acknowledgements', content='Acknowledgements')
        # self.send_ck_content(outer_id='cke_id_conflicts_of_interest', content='Conflicts of Interest')
        # self.selenium.find_element_by_id('add-reference-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_project-reference-content_type-object_id-0-description')))
        # element.send_keys('Reference 1')
        # self.selenium.find_element_by_id('add-reference-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_project-reference-content_type-object_id-1-description')))
        # self.selenium.find_element_by_name('edit_description').click()

        # # Access
        # self.selenium.find_element_by_id('access_tab').click()
        # Select(self.selenium.find_element_by_name('license')).select_by_visible_text('Creative Commons Attribution 4.0 International Public License')
        # self.selenium.find_element_by_name('edit_access').click()

        # # Identifiers
        # self.selenium.find_element_by_id('identifiers_tab').click()
        # self.selenium.find_element_by_id('id_project_home_page').send_keys('https://physionet.org')
        # self.selenium.find_element_by_id('add-publication-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_project-publication-content_type-object_id-0-citation')))
        # element.send_keys('Citation')
        # self.selenium.find_element_by_id('id_project-publication-content_type-object_id-0-url').send_keys('https://google.com')
        # self.selenium.find_element_by_id('add-topic-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_project-topic-content_type-object_id-0-description')))
        # element.send_keys('Topic 1')
        # self.selenium.find_element_by_id('add-topic-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'id_project-topic-content_type-object_id-1-description')))
        # element.send_keys('Topic 2')
        # self.selenium.find_element_by_name('edit_identifiers').click()

        # # Files - Create 2 folders, rename one, delete one, navigate to one.
        # self.selenium.find_element_by_id('files_tab').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'request-storage-button')))
        # self.selenium.find_element_by_id('request-storage-button').click()
        # self.selenium.find_element_by_id('id_request_allowance').send_keys(10)
        # self.selenium.find_element_by_id('request-storage-button-submit').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'create-folder-button')))
        # self.selenium.find_element_by_id('create-folder-button').click()
        # self.selenium.find_element_by_id('id_folder_name').send_keys('subject-1')
        # self.selenium.find_element_by_id('create-folder-button-submit').click()
        # self.selenium.find_element_by_name('items').click()
        # self.selenium.find_element_by_id('rename-item-button').click()
        # self.selenium.find_element_by_id('id_new_name').send_keys('subject-10')
        # self.selenium.find_element_by_id('rename-item-button-submit').click()
        # self.selenium.find_element_by_id('create-folder-button').click()
        # self.selenium.find_element_by_id('id_folder_name').send_keys('subject-2')
        # self.selenium.find_element_by_id('create-folder-button-submit').click()
        # # Instead of uploading files via form, just create some for now
        # project = ActiveProject.objects.get(title='Data Project 1')
        # with open(os.path.join(project.file_root(), 'subject-info.csv'), 'w') as f:
        #     f.write('number,age,gender\n10,50,F')
        # with open(os.path.join(project.file_root(), 'subject-10', '10.txt'), 'w') as f:
        #     f.write('subject 10 from hospital\n')

        # # Proofread/preview
        # self.selenium.find_element_by_id('proofread_tab').click()
        # self.selenium.find_element_by_id('view_preview').click()
        # self.selenium.switch_to.window(self.selenium.window_handles[0])

        # # Accept author invitation as aewj
        # self.selenium_login(username='aewj', password='Tester11!', new=True)
        # self.selenium.find_element_by_id('respond_button_{}'.format(project.id)).click()
        # self.selenium.find_element_by_name('invitation_response').click()

        # # Approve storage request as admin
        # self.selenium_login(username='admin', password='Tester11!', new=True)
        # self.selenium.find_element_by_id('nav_account_dropdown').click()
        # self.selenium.find_element_by_id('nav_admin').click()
        # self.selenium.find_element_by_id('nav_storage_requests').click()
        # storage_request = StorageRequest.objects.get(project=project)
        # self.selenium.find_element_by_id('respond-modal-button-{}'.format(storage_request.id)).click()
        # self.selenium.find_element_by_id('storage-response-button-{}'.format(storage_request.id)).click()

        # # Finish submitting project as rgmark
        # self.selenium_login(username='rgmark', password='Tester11!', new=True)
        # self.selenium.find_element_by_link_text('Data Project 1').click()
        # self.selenium.find_element_by_id('submission_tab').click()
        # self.selenium.find_element_by_id('submit-project-modal-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'submit-project-button')))
        # element.click()

        # # Test state of project. Submission may take time to run submit.
        # timeout = time.time() + 10
        # project = ActiveProject.objects.get(title='Data Project 1')
        # while not project.under_submission():
        #     project = ActiveProject.objects.get(title='Data Project 1')
        #     if time.time() > timeout:
        #         break
        # self.assertTrue(project.under_submission())
        # self.assertEqual(project.storage_used(), 50)

    def Test_publish(self):
        """
        Test steps from submission to publication

        """
        pass
        # # Submit
        # self.selenium_login(username='rgmark', password='Tester11!')
        # self.selenium.find_element_by_link_text('MIT-BIH Arrhythmia Database').click()
        # self.selenium.find_element_by_id('submission_tab').click()
        # self.selenium.find_element_by_id('submit-project-modal-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'submit-project-button')))
        # self.selenium.find_element_by_id('id_author_comments').send_keys('Everything is impeccable.')
        # element.click()

        # # Assign editor and request revisions
        # self.selenium_login(username='admin', password='Tester11!', new=True)
        # self.selenium.find_element_by_id('nav_account_dropdown').click()
        # self.selenium.find_element_by_id('nav_admin').click()
        # self.selenium.find_element_by_id('nav_submitted_projects').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'assign-editor-modal-button')))
        # self.selenium.find_element_by_id('assign-editor-modal-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'id_editor')))
        # Select(self.selenium.find_element_by_id(
        #     'id_project')).select_by_visible_text('MIT-BIH Arrhythmia Database')
        # Select(self.selenium.find_element_by_id(
        #     'id_editor')).select_by_visible_text('admin')
        # self.selenium.find_element_by_name('assign_editor').click()
        # self.selenium.find_element_by_id('nav_editor_home').click()
        # self.selenium.find_element_by_link_text('Edit Project').click()
        # for field in ['soundly_produced', 'well_described', 'open_format',
        #     'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable']:
        #     Select(self.selenium.find_element_by_id(
        #         'id_{}'.format(field))).select_by_visible_text('No')
        # self.selenium.find_element_by_id('id_editor_comments').send_keys('Everything is bad.')
        # Select(self.selenium.find_element_by_id(
        #         'id_decision'.format(field))).select_by_visible_text('Resubmit with revisions')
        # project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        # self.assertFalse(project.author_editable())
        # self.selenium.find_element_by_name('submit_response').click()

        # # Author edits content and resubmits
        # self.selenium_login(username='rgmark', password='Tester11!', new=True)
        # self.selenium.find_element_by_link_text('MIT-BIH Arrhythmia Database').click()
        # self.selenium.find_element_by_id('content_tab').click()
        # self.selenium.find_element_by_id('id_version').clear()
        # self.selenium.find_element_by_id('id_version').send_keys('1.0.1')
        # self.selenium.find_element_by_name('edit_description').click()
        # self.selenium.find_element_by_id('submission_tab').click()
        # self.selenium.find_element_by_id('resubmit-project-modal-button').click()
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.element_to_be_clickable((By.ID, 'resubmit-project-button')))
        # self.selenium.find_element_by_id('id_author_comments').send_keys('Even more impeccable.')
        # element.click()

        # # Editor accepts
        # self.selenium_login(username='admin', password='Tester11!', new=True)
        # self.selenium.find_element_by_id('nav_account_dropdown').click()
        # self.selenium.find_element_by_id('nav_admin').click()
        # self.selenium.find_element_by_id('nav_editor_home').click()
        # self.selenium.find_element_by_link_text('Edit Project').click()
        # for field in ['soundly_produced', 'well_described', 'open_format',
        #     'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable']:
        #     Select(self.selenium.find_element_by_id(
        #         'id_{}'.format(field))).select_by_visible_text('Yes')
        # self.selenium.find_element_by_id('id_editor_comments').send_keys('Thanks for fixing.')
        # Select(self.selenium.find_element_by_id(
        #         'id_decision'.format(field))).select_by_visible_text('Accept')
        # self.selenium.find_element_by_name('submit_response').click()

        # # Editor copyedits the submission, creating a folder.
        # self.selenium.find_element_by_link_text('copyedit').click()
        # self.selenium.find_element_by_link_text('subject-100').click()
        # self.selenium.find_element_by_id('create-folder-button').click()
        # self.selenium.find_element_by_id('id_folder_name').send_keys('secret-info')
        # self.selenium.find_element_by_id('create-folder-button-submit').click()

        # element = WebDriverWait(self.selenium, 20).until(
        #         EC.element_to_be_clickable((By.LINK_TEXT, 'Parent Directory')))
        # self.selenium.find_element_by_link_text('Parent Directory').click()
        # self.selenium.find_element_by_link_text('Complete Copyedit').click()
        # Select(self.selenium.find_element_by_id(
        #         'id_made_changes'.format(field))).select_by_visible_text('Yes')
        # self.selenium.find_element_by_id('id_changelog_summary').send_keys('Created an empty folder.')
        # self.selenium.find_element_by_name('complete_copyedit').click()

        # # Editor reopens copyedit, edits some metadata, and completes it again
        # self.selenium.find_element_by_link_text('editor home').click()
        # self.selenium.find_element_by_link_text('View Authors').click()
        # self.selenium.find_element_by_id('reopen-copyedit-modal-button').click()
        # self.selenium.find_element_by_name('reopen_copyedit').click()
        # self.selenium.find_element_by_link_text('copyediting').click()

        # self.selenium.find_element_by_link_text('Edit Content').click()
        # self.send_ck_content(outer_id='cke_id_release_notes', content='This is a stable release.')
        # self.selenium.find_element_by_link_text('Complete Copyedit').click()
        # Select(self.selenium.find_element_by_id(
        #     'id_made_changes'.format(field))).select_by_visible_text('Yes')
        # self.selenium.find_element_by_id('id_changelog_summary').send_keys('Added release notes.')
        # self.selenium.find_element_by_name('complete_copyedit').click()

        # # Author approves publication
        # self.selenium_login(username='rgmark', password='Tester11!', new=True)
        # self.selenium.find_element_by_link_text('MIT-BIH Arrhythmia Database').click()
        # self.selenium.find_element_by_id('submission_tab').click()
        # self.selenium.find_element_by_id('approve-publication-modal-button').click()
        # self.selenium.find_element_by_id('approve-publication-button').click()

        # # Editor publishes
        # self.selenium_login(username='admin', password='Tester11!', new=True)
        # self.selenium.find_element_by_id('nav_account_dropdown').click()
        # self.selenium.find_element_by_id('nav_admin').click()
        # self.selenium.find_element_by_id('nav_editor_home').click()
        # self.selenium.find_element_by_link_text('Publish Project').click()
        # self.selenium.find_element_by_id('id_doi').send_keys('10.13026/MIT505')
        # Select(self.selenium.find_element_by_id(
        #     'id_make_zip'.format(field))).select_by_visible_text('Yes')
        # self.selenium.find_element_by_name('publish_submission').click()

        # # Visit the page and click some links. Assert that the project is
        # # published and the files are present and accessible
        # self.selenium.find_element_by_link_text('here').click()
        # self.assertFalse(ActiveProject.objects.filter(title='MIT-BIH Arrhythmia Database'))
        # project = PublishedProject.objects.get(title='MIT-BIH Arrhythmia Database', version='1.0.1')
        # element = WebDriverWait(self.selenium, 20).until(
        #     EC.presence_of_element_located((By.ID, 'files')))
        # self.selenium.find_element_by_link_text('subject-100').click()
        # self.selenium.find_element_by_link_text('Parent Directory').click()
        # self.selenium.find_element_by_link_text('sha256sums.txt').click()
