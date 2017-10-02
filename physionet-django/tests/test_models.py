from django.test import TestCase
from user.models import User
from project.models import Project
from user.models import User
# from django.core import management

class TestModels(TestCase):
    """
    The TestCase class includes self.client, so no need to set up a client.
    """
    def setUp(self):
        """
        Should update to use management command
        management.call_command('loaddata', 'user', verbosity=1)
        """
        user0 = User.objects.create_superuser(email="tester@mit.edu", 
            password="Tester1!")
        user0.save()

    def tearDown(self):
        pass

    def test_user_login(self):
        """
        Test that known users are able to login.
        """
        unknown_user = self.client.login(username='what', 
            password='letmein')
        known_admin_user = self.client.login(username='tester@mit.edu', 
            password='Tester1!')
        self.assertEqual(False, unknown_user)
        self.assertEqual(True, known_admin_user)
