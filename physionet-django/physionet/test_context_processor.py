from django.test import TestCase
from unittest import mock

from physionet.models import StaticPage
from physionet import context_processors


class TestContextProcessor(TestCase):
    """ For testing the context processors"""

    def test_static_pages_cp(self):
        """ Tests the static_pages context processor"""

        static_page_obj = StaticPage.objects.all().order_by('nav_order')
        resp = context_processors.static_pages(mock.Mock)

        self.assertQuerysetEqual(resp['static_pg'], static_page_obj, transform=lambda x: x)
