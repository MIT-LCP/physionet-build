from django.test import TestCase, override_settings
from django.urls import reverse

from physionet.context_processors import static_or_url


@override_settings(STATIC_URL='/static/')
class TestStaticOrUrl(TestCase):
    def test_static_path(self):
        self.assertEqual(static_or_url('images/banner.webp'), '/static/images/banner.webp')

    def test_full_url(self):
        url = 'https://example.org/banner.jpg'
        self.assertEqual(static_or_url(url), url)

    def test_root_relative_url(self):
        self.assertEqual(static_or_url('/media/banner.jpg'), '/media/banner.jpg')


class TestHomepageBannerImage(TestCase):
    def test_default_banner(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, "url('/static/images/banner.webp')")

    @override_settings(HOMEPAGE_BANNER_IMAGE='https://example.org/banner.jpg')
    def test_custom_banner_url(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, "url('https://example.org/banner.jpg')")
        self.assertNotContains(response, 'images/banner.webp')
