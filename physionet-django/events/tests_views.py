import datetime
import logging

from django.urls import reverse

from events.models import CohostInvitation, Event, EventApplication, EventParticipant
from user.models import User
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


class TestEventCohosts(TestMixin):
    """Test what hosts and cohosts can do to manage an event"""

    def setUp(self):
        super().setUp()
        self.host = User.objects.get(username='admin')
        self.cohost = User.objects.get(username='george')
        self.participant = User.objects.get(username='aewj')
        self.other_participant = User.objects.get(username='jameslawson')

        self.event = Event.objects.create(
            title='Cohost test event',
            category='Course',
            host=self.host,
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=7),
            gcp_billing_id='billing-123',
        )
        EventParticipant.objects.create(event=self.event, user=self.cohost, is_cohost=True)
        EventParticipant.objects.create(event=self.event, user=self.participant)
        EventParticipant.objects.create(event=self.event, user=self.other_participant)
        self.detail_url = reverse('event_detail', kwargs={'event_slug': self.event.slug})
        self.edit_url = reverse('update_event', kwargs={'event_slug': self.event.slug})

    def login(self, user):
        self.client.login(username=user.username, password='Tester11!')

    def edit_data(self, title):
        return {
            'title': title,
            'description': 'Updated description',
            'start_date': self.event.start_date.strftime("%Y-%m-%d"),
            'end_date': self.event.end_date.strftime("%Y-%m-%d"),
            'category': 'Course',
            'allowed_domains': '',
        }

    def test_is_host_or_cohost(self):
        self.assertTrue(self.event.is_host_or_cohost(self.host))
        self.assertTrue(self.event.is_host_or_cohost(self.cohost))
        self.assertFalse(self.event.is_host_or_cohost(self.participant))
        self.assertFalse(self.event.is_cohost(self.host))

    def test_cohost_can_edit_event_without_permission(self):
        self.assertFalse(self.cohost.has_perm('events.add_event'))
        self.login(self.cohost)

        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(self.edit_url, data=self.edit_data('Renamed by cohost'))
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Renamed by cohost')
        # the event still belongs to the host, and billing is unchanged
        self.assertEqual(self.event.host, self.host)
        self.assertEqual(self.event.gcp_billing_id, 'billing-123')

    def test_cohost_edit_checks_titles_of_host_events(self):
        Event.objects.create(title='Another host event', category='Course', host=self.host)
        self.login(self.cohost)
        response = self.client.post(self.edit_url, data=self.edit_data('Another host event'))
        self.assertContains(response, 'Event with this title already exists')
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Cohost test event')

    def test_participant_cannot_edit_event(self):
        self.login(self.participant)

        response = self.client.get(self.edit_url)
        self.assertRedirects(response, self.detail_url)

        self.client.post(self.edit_url, data=self.edit_data('Renamed by participant'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Cohost test event')

    def test_cohost_sees_host_controls(self):
        self.login(self.cohost)
        response = self.client.get(self.detail_url)
        self.assertContains(response, 'billing-123')
        self.assertContains(response, 'Invite Co-Host')

        response = self.client.get(reverse('event_home'))
        self.assertContains(response, f'#participants-modal-{self.event.id}')
        self.assertContains(response, self.edit_url)

    def test_participant_does_not_see_host_controls(self):
        self.login(self.participant)
        response = self.client.get(self.detail_url)
        self.assertNotContains(response, 'billing-123')
        self.assertNotContains(response, 'Invite Co-Host')

        response = self.client.get(reverse('event_home'))
        self.assertNotContains(response, f'#participants-modal-{self.event.id}')
        self.assertNotContains(response, self.edit_url)

    def test_cohost_can_see_past_event_participants(self):
        self.event.start_date = datetime.date.today() - datetime.timedelta(days=14)
        self.event.end_date = datetime.date.today() - datetime.timedelta(days=7)
        self.event.save()
        self.login(self.cohost)
        response = self.client.get(reverse('event_home'))
        self.assertContains(response, f'#participants-modal-{self.event.id}')

    def test_cohost_can_invite_and_cancel_cohost(self):
        self.login(self.cohost)
        response = self.client.post(self.detail_url, data={
            'email': self.participant.email, 'invite_cohost': ''})
        self.assertEqual(response.status_code, 200)
        invitation = CohostInvitation.objects.get(event=self.event, email=self.participant.email)

        self.client.post(self.detail_url, data={'cancel_invitation': invitation.id})
        self.assertFalse(CohostInvitation.objects.filter(id=invitation.id).exists())

    def test_participant_cannot_invite_or_cancel(self):
        invitation = CohostInvitation.objects.create(event=self.event, email=self.other_participant.email)
        self.login(self.participant)

        self.client.post(self.detail_url, data={
            'email': self.participant.email, 'invite_cohost': ''})
        self.assertFalse(CohostInvitation.objects.filter(email=self.participant.email).exists())

        self.client.post(self.detail_url, data={'cancel_invitation': invitation.id})
        self.assertTrue(CohostInvitation.objects.filter(id=invitation.id).exists())

    def test_host_can_remove_cohost(self):
        cohost_participant = self.event.participants.get(user=self.cohost)
        self.login(self.host)
        response = self.client.post(self.detail_url, data={'remove_cohost': cohost_participant.id})
        self.assertRedirects(response, self.detail_url)
        cohost_participant.refresh_from_db()
        self.assertFalse(cohost_participant.is_cohost)

    def test_cohost_can_step_down(self):
        cohost_participant = self.event.participants.get(user=self.cohost)
        self.login(self.cohost)
        self.client.post(self.detail_url, data={'remove_cohost': cohost_participant.id})
        cohost_participant.refresh_from_db()
        self.assertFalse(cohost_participant.is_cohost)
        # stepping down keeps the user registered for the event
        self.assertTrue(self.event.participants.filter(user=self.cohost).exists())

    def test_cohost_cannot_remove_other_cohost(self):
        other = self.event.participants.get(user=self.other_participant)
        other.make_cohost()
        self.login(self.cohost)
        self.client.post(self.detail_url, data={'remove_cohost': other.id})
        other.refresh_from_db()
        self.assertTrue(other.is_cohost)
