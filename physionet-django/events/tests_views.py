import datetime
import logging

from django.urls import reverse

from events.models import Event
from user.test_views import TestMixin


class TestEvents(TestMixin):
    """ Test that all views are behaving as expected """

    def setUp(self):
        """Setup for tests"""

        super().setUp()
        self.new_event_name = "test event"
        self.updated_event_name = "updated test event"
        self.new_event_start_date = datetime.date.today() + datetime.timedelta(days=7)
        self.new_event_end_date = datetime.date.today() + datetime.timedelta(days=14)
        self.new_event_start_date_str = self.new_event_start_date.strftime("%Y-%m-%d")
        self.new_event_end_date_str = self.new_event_end_date.strftime("%Y-%m-%d")

        self.client.login(username='admin', password='Tester11!')

    def test_add_event_valid(self):
        """tests the view that adds an event"""

        # Create an event
        response = self.client.post(
            reverse('event_home'),
            data={
                'title': self.new_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': ''
            })

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title=self.new_event_name)
        self.assertEqual(event.title, self.new_event_name)

    def test_add_event_invalid(self):
        """tests the view that adds an invalid event(event with duplicate title for same host)"""

        # Create an event
        self.test_add_event_valid()

        # Create another event with same title
        response = self.client.post(
            reverse('event_home'),
            data={
                'title': self.new_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit2.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': ''
            })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/event_home.html')
        self.assertContains(response, 'Event with this title already exists')

    def test_edit_event_valid(self):
        """edits an existing event"""

        # add an event first
        self.test_add_event_valid()
        event = Event.objects.get(title=self.new_event_name)
        slug = event.slug

        response = self.client.post(
            reverse('update_event', kwargs={'event_slug': slug}),
            data={
                'title': self.updated_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': ''
            })

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title=self.updated_event_name)
        self.assertEqual(event.title, self.updated_event_name)

    def test_edit_event_invalid(self):
        """tests the view that edits an invalid event(event with duplicate title for same host)"""

        # add an event first
        self.test_add_event_valid()
        event = Event.objects.get(title=self.new_event_name)
        slug = event.slug

        # Create another event with another title
        response = self.client.post(
            reverse('event_home'),
            data={
                'title': self.updated_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': ''
            })

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title=self.new_event_name)
        self.assertEqual(event.title, self.new_event_name)

        # try to edit the first event with the title of the second event
        response = self.client.post(
            reverse('update_event', kwargs={'event_slug': slug}),
            data={
                'title': self.updated_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Workshop',
                'allowed_domains': ''
            })

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(slug=slug)
        self.assertEqual(event.title, self.new_event_name)
