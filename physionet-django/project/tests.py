import os
import pdb
import shutil

from django.conf import settings
from django.test import TestCase, override_settings

from project.models import ActiveProject, PublishedProject



# def replace_project():
#     """
#     Function for testing project content


#     """



# def copy_demo_media(subdir):
#     "Copy the demo content from the specified subdirectory"
#     demo_subdir = os.path.join(settings.MEDIA_ROOT, 'demo', subdir)
#     target_subdir = os.path.join(settings.MEDIA_ROOT, subdir)

#     for item in os.listdir(demo_subdir):
#         shutil.copytree(os.path.join(demo_subdir, item),
#                         os.path.join(target_subdir, item))



class TestOne(TestCase):
    """
    Because the fixtures are installed and database is rolled back
    before each setup and teardown respectively, the demo test files
    will be created and destroyed after each test also. We want the
    demo files as well as the demo data reset each time, and individual
    test methods such as publishing projects may change the files.

    """
    fixtures = ['demo-user', 'demo-project']

    # @classmethod
    # def setUpClass(cls):
    #     """

    #     """
    #     super().setUpClass()


    # @classmethod
    # def tearDownClass(cls):
    #     super().setUpClass()

    def setUp(self):
        """
        Copy the demo files to the testing root
        """
        shutil.copytree(os.path.abspath(os.path.join(settings.MEDIA_ROOT, '../demo')),
            settings.MEDIA_ROOT)

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT)

    def test_one(self):
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        pdb.set_trace()
