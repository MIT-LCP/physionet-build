from django.test import TestCase
from user.models import User
from project.models import Project

class TestViews(TestCase):
    """
    The TestCase class includes self.client, so no need to set up a client.
    """
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_root_webpage_is_found(self):
        """
        Test that the root/home webpage returns a 200 code.
        """
        response = self.client.get('/')
        self.assertEqual(200, response.status_code)

    def test_admin_page_redirects_to_login(self):
        """
        Test that the root/home webpage redirects to a login page.
        """
        response = self.client.get('/admin/')
        redirect_url = response['Location'].split('?')[0]
        self.assertEqual('/admin/login/', redirect_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response,'/admin/login/?next=/admin/',
            status_code=302)
