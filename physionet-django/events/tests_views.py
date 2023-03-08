import datetime
import logging

from django.urls import reverse

from events.models import Event, EventApplication
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
            reverse('create_event'),
            data={
                'title': self.new_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': '',
                'add-event': ''
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
            reverse('create_event'),
            data={
                'title': self.new_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit2.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': '',
                'add-event': ''
            })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/event_create.html')
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
            reverse('create_event'),
            data={
                'title': self.updated_event_name,
                'description': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                'start_date': self.new_event_start_date_str,
                'end_date': self.new_event_end_date_str,
                'category': 'Course',
                'allowed_domains': '',
                'add-event': ''
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

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/event_edit.html')
        self.assertContains(response, 'Event with this title already exists')
        event = Event.objects.get(slug=slug)
        self.assertEqual(event.title, self.new_event_name)

    def test_event_participation_join_waitlist(self):
        """tests the view that adds a user to the waitlist of an event"""

        # add an event first
        self.test_add_event_valid()
        event = Event.objects.get(title=self.new_event_name)
        slug = event.slug

        # login as a user and try to join the event
        self.client.login(username='amitupreti', password='Tester11!')
        # add a user to the waitlist
        response = self.client.post(
            reverse('event_detail', kwargs={'event_slug': slug}),
            data={
                'confirm_registration': ''
            })
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()

        # check if the user is added to the waitlist
        EventApplication.objects.get(
            event=event,
            user__username='amitupreti',
            status=EventApplication.EventApplicationStatus.WAITLISTED
        )

    def test_event_participation_withdraw(self):
        """tests the view that withdraws a user from an event"""

        # Create an event, add a user to the waitlist
        self.test_event_participation_join_waitlist()

        event = Event.objects.get(title=self.new_event_name)
        # add a user to the waitlist
        response = self.client.post(
            reverse('event_detail', kwargs={'event_slug': event.slug}),
            data={
                'confirm_withdraw': ''
            })
        self.assertEqual(response.status_code, 302)

        # check if the user application is withdrawn
        EventApplication.objects.get(
            event=event,
            user__username='amitupreti',
            status=EventApplication.EventApplicationStatus.WITHDRAWN
        )

    def test_event_participation_approved(self):
        """tests the view that approves a user for an event"""

        # create an event, and add a user to the waitlist and verify that the user is added to the waitlist
        self.test_event_participation_join_waitlist()

        event = Event.objects.get(title=self.new_event_name)

        # login as the host and approve the user
        self.client.login(username='admin', password='Tester11!')

        # get event application
        event_application = EventApplication.objects.get(
            event=event,
            user__username='amitupreti',
            status=EventApplication.EventApplicationStatus.WAITLISTED
        )

        # approve the user
        response = self.client.post(
            reverse('event_home'),
            data={
                'form-TOTAL_FORMS': ['1'],
                'form-INITIAL_FORMS': ['1'],
                'form-MIN_NUM_FORMS': ['0'],
                'form-MAX_NUM_FORMS': ['1000'],
                'form-0-status': ['AP'],
                'form-0-comment_to_applicant': ['Great Job! Welcome to the event!'],
                'form-0-id': [f'{event_application.id}'],
                'participation_response': [f'{event_application.id}']
            }
        )
        self.assertEqual(response.status_code, 302)

        # check if the user was approved
        event.refresh_from_db()
        event.participants.get(user__username='amitupreti')

    def test_event_participation_rejected(self):
        """tests the view that rejects a user for an event"""

        # create an event, and add a user to the waitlist and verify that the user is added to the waitlist
        self.test_event_participation_join_waitlist()

        event = Event.objects.get(title=self.new_event_name)

        # login as the host and reject the user
        self.client.login(username='admin', password='Tester11!')

        # get event application
        event_application = EventApplication.objects.get(
            event=event,
            user__username='amitupreti',
            status=EventApplication.EventApplicationStatus.WAITLISTED
        )

        # reject the user
        response = self.client.post(
            reverse('event_home'),
            data={
                'form-TOTAL_FORMS': ['1'],
                'form-INITIAL_FORMS': ['1'],
                'form-MIN_NUM_FORMS': ['0'],
                'form-MAX_NUM_FORMS': ['1000'],
                'form-0-status': ['NA'],
                'form-0-comment_to_applicant': ['Sorry, you were not selected for the event!'],
                'form-0-id': [f'{event_application.id}'],
                'participation_response': [f'{event_application.id}']
            }
        )
        self.assertEqual(response.status_code, 302)

        # check if the user was rejected
        event.refresh_from_db()

        self.assertEqual(event.participants.filter(user__username='amitupreti').count(), 0)

        # check the status on the event application
        event_application.refresh_from_db()
        self.assertEqual(event_application.status, EventApplication.EventApplicationStatus.NOT_APPROVED)
