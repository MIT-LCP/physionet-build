from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from django.urls import reverse
from django.db import transaction
from django.utils import timezone


import notification.utility as notification
from project.utility import get_form_errors
from events.forms import AddEventForm, EventApplicationResponseForm, InviteCohostForm, CohostInvitationResponseForm
from events.models import Event, EventApplication, EventParticipant, CohostInvitation
from events.utility import notify_host_cohosts_new_registration
from project.forms import InvitationResponseForm
from django.http import Http404


@login_required
def update_event(request, event_slug, **kwargs):
    user = request.user
    can_change_event = user.has_perm('events.add_event')
    event = Event.objects.get(slug=event_slug)
    if request.method == 'POST':
        event_form = AddEventForm(user=user, data=request.POST, instance=event)
        if event_form.is_valid():
            if can_change_event and event.host == user:
                event_form.save()
                messages.success(request, "Updated Event Successfully")
            else:
                messages.error(request, "You don't have permission to edit this event")
            return redirect(event_home)
        else:
            messages.error(request, event_form.errors)
    else:
        event_form = AddEventForm(instance=event, user=user)

    return render(
        request, 'events/event_edit.html', {'event': event, 'event_form': event_form})


@login_required
def create_event(request):
    """
    Adds an event
    """
    user = request.user
    can_change_event = user.has_perm('events.add_event')
    if not can_change_event:
        messages.error(request, "You don't have permission to add an event")
        return redirect(event_home)

    if request.method == 'POST':
        event_form = AddEventForm(user=user, data=request.POST)
        if event_form.is_valid():
            event_form.save()
            messages.success(request, "Added Event Successfully")
            return redirect(event_home)
        else:
            messages.error(request, event_form.errors)
    else:
        event_form = AddEventForm(user=user)

    return render(
        request, 'events/event_create.html', {'event_form': event_form})


@login_required
def get_event_details(request, event_slug):
    can_change_event = request.user.has_perm('events.add_event')
    if not can_change_event:
        return JsonResponse([{'error': 'You don\'t have permission to access event'}], safe=False)
    event = Event.objects.filter(slug=event_slug).values()
    return JsonResponse(list(event), safe=False)


@login_required
def event_home(request):
    """
    List of events
    """
    user = request.user
    can_change_event = user.has_perm("events.add_event")

    EventApplicationResponseFormSet = modelformset_factory(
        EventApplication, form=EventApplicationResponseForm, extra=0
    )
    InvitationResponseFormSet = modelformset_factory(
        CohostInvitation, form=CohostInvitationResponseForm, extra=0
    )

    # sqlite doesn't support the distinct() method
    events_all = Event.objects.filter(Q(host=user) | Q(participants__user=user))
    # concatenate the events where the user is the host,participant and the events where the user is on the waitlist
    events_all = events_all | Event.objects.filter(
        applications__user=user,
        applications__status=EventApplication.EventApplicationStatus.WAITLISTED,
    )

    events_active = set(events_all.filter(end_date__gte=datetime.now()))
    events_past = set(events_all.filter(end_date__lt=datetime.now()))
    event_form = AddEventForm(user=user)

    url_prefix = notification.get_url_prefix(request)

    form_error = False

    cohost_ids = EventParticipant.objects.filter(
        user=user, is_cohost=True).values_list("event__id", flat=True)

    # handle notifications to join an event
    if request.method == "POST" and "participation_response" in request.POST.keys():
        formset = EventApplicationResponseFormSet(request.POST)
        # only process the form that was submitted
        for form in formset:
            if form.instance.id != int(request.POST["participation_response"]):
                continue

            if not form.is_valid():
                messages.error(request, form.errors)
                return redirect(event_home)

            event_application = form.save(commit=False)
            event = event_application.event
            # if user is not a host or a participant with cohort status, they don't have permission to accept/reject
            if not (
                event.host == user
                or EventParticipant.objects.filter(
                    event=event, user=user, is_cohost=True
                ).exists()
            ):
                messages.error(
                    request,
                    "You don't have permission to accept/reject this application",
                )
                return redirect(event_home)
            elif (
                event_application.status
                == EventApplication.EventApplicationStatus.APPROVED
            ):
                if EventParticipant.objects.filter(
                    event=event, user=event_application.user
                ).exists():
                    messages.error(request, "Application was already approved")
                    return redirect(event_home)
                event_application.accept(
                    comment_to_applicant=form.cleaned_data.get("comment_to_applicant")
                )
                notification.notify_participant_event_decision(
                    request=request,
                    user=event_application.user,
                    event=event_application.event,
                    decision=EventApplication.EventApplicationStatus.APPROVED.label,
                    comment_to_applicant=form.cleaned_data.get("comment_to_applicant"),
                )
            elif (
                event_application.status
                == EventApplication.EventApplicationStatus.NOT_APPROVED
            ):
                event_application.reject(
                    comment_to_applicant=form.cleaned_data.get("comment_to_applicant")
                )
                notification.notify_participant_event_decision(
                    request=request,
                    user=event_application.user,
                    event=event_application.event,
                    decision=EventApplication.EventApplicationStatus.NOT_APPROVED.label,
                    comment_to_applicant=form.cleaned_data.get("comment_to_applicant"),
                )

            return redirect(event_home)
        else:
            form_error = True
    elif request.method == "POST" and 'invitation_response' in request.POST.keys():
        host_qs = CohostInvitation.get_user_invitations(user)
        invitation_response_formset = InvitationResponseFormSet(
            request.POST,
            queryset=host_qs,
        )
        if process_invitation_response(request, invitation_response_formset):
            return redirect('event_home')

    events = Event.objects.all().prefetch_related(
        "participants",
        "applications",
    )

    event_details = {}
    for event in events:
        applications = event.applications.all()
        pending_applications = [
            application
            for application in applications
            if application.status == EventApplication.EventApplicationStatus.WAITLISTED
        ]
        rejected_applications = [
            application
            for application in applications
            if application.status == EventApplication.EventApplicationStatus.NOT_APPROVED
        ]
        withdrawn_applications = [
            application
            for application in applications
            if application.status == EventApplication.EventApplicationStatus.WITHDRAWN
        ]

        event_details[event.id] = [
            {
                "id": "participants",
                "title": "Total participants:",
                "count": len(event.participants.all()),
                "objects": event.participants.all(),
            },
            {
                "id": "pending_applications",
                "title": "Pending applications:",
                "count": len(pending_applications),
                "objects": pending_applications,
            },
            {
                "id": "rejected_applications",
                "title": "Rejected applications:",
                "count": len(rejected_applications),
                "objects": rejected_applications,
            },
            {
                "id": "withdrawn_applications",
                "title": "Withdrawn applications:",
                "count": len(withdrawn_applications),
                "objects": withdrawn_applications,
            },
        ]

    # get all participation requests for Active events where the current user is the host and the participants are
    # waiting for a response

    # making the query to get all the participation requests for the events
    # where the user is the host or an event participant with cohort status
    participation_requests = EventApplication.objects.filter(
        Q(event__host=user) | Q(event__id__in=cohost_ids),
        status=EventApplication.EventApplicationStatus.WAITLISTED,
        event__end_date__gte=datetime.now(),
    )

    participation_response_formset = EventApplicationResponseFormSet(
        queryset=participation_requests
    )
    invitation_response_formset = InvitationResponseFormSet(
        queryset=CohostInvitation.get_user_invitations(user))

    return render(
        request,
        "events/event_home.html",
        {
            "events_active": events_active,
            "events_past": events_past,
            "event_form": event_form,
            "url_prefix": url_prefix,
            "can_change_event": can_change_event,
            "form_error": form_error,
            "participation_response_formset": participation_response_formset,
            "invitation_response_formset": invitation_response_formset,
            "event_details": event_details,
        },
    )


def cancel_invitation(request, invitation_id, event):
    """
    Cancel an invitation to become a cohost
    """
    user = request.user
    invitation = CohostInvitation.objects.get(id=invitation_id)

    if invitation.event == event:
        if user == event.host:
            invitation.delete()
            messages.success(request, "Invitation has been successfully cancelled")
        else:
            messages.error(request, "You don't have permission to cancel this invitation")
    else:
        messages.error(request, "Invalid invitation")


def process_invitation_response(request, invitation_response_formset):
    """
    Process an invitation response
    Helper function for event_detail

    if an invitation is accepted, the user is added as a cohost
    otherwise, return None
    """
    user = request.user
    invitation_id = int(request.POST["invitation_response"])
    for invitation_response_form in invitation_response_formset:
        # only process the response that was submitted
        if invitation_response_form.instance.id == invitation_id:
            break
        else:
            return None

    if invitation_response_form.is_valid():
        with transaction.atomic():
            invitation = invitation_response_form.instance
            event = invitation.event
            invitations = CohostInvitation.objects.filter(
                is_active=True, email__in=user.get_emails(), event=event)
            affected_emails = [i.email for i in invitations]
            invitations.update(
                response=invitation.response,
                response_datetime=timezone.now(),
                is_active=False,
            )
            if invitation.response:
                participant = EventParticipant.objects.get(event=event, user=user)
                participant.is_cohost = True
                participant.save()

            notification.cohost_response_notify(invitation, affected_emails)

            messages.success(request, "The invitation has been {0}".format(
                notification.RESPONSE_ACTIONS[invitation.response]))

            if invitation.response:
                return True
            else:
                return None
    else:
        messages.error(request, get_form_errors(invitation_response_form))
        return None


@login_required
def event_detail(request, event_slug):
    """
    Detail page of an event
    """
    user = request.user

    event = get_object_or_404(Event, slug=event_slug)

    registration_allowed = True
    is_waitlisted = False
    registration_error_message = ''
    invite_cohost_form = None
    invitation_response_formset = None

    InvitationResponseFormSet = modelformset_factory(CohostInvitation,
                                                     form=CohostInvitationResponseForm,
                                                     extra=0)

    # if the event has ended, registration is not allowed, so we can skip the rest of the checks
    if event.end_date < datetime.now().date():
        registration_allowed = False
        registration_error_message = 'Registration is closed. Event has ended.'
    elif event.host == user:
        registration_allowed = False
        registration_error_message = 'You are the host of this event'
        invite_cohost_form = InviteCohostForm(event=event)
    elif event.participants.filter(user=user).exists():
        registration_allowed = False
        registration_error_message = 'You are registered for this event'
        invitation_response_formset = InvitationResponseFormSet(
            queryset=CohostInvitation.get_user_invitations(user))
    else:  # we don't need to check for waitlisted / other stuff if the user is already registered
        event_participation_request = EventApplication.objects.filter(
            event=event,
            user=user,
            status=EventApplication.EventApplicationStatus.WAITLISTED)
        # currently we are not blocking rejected, revoked access users from registering again
        if event_participation_request.exists():
            registration_allowed = False
            is_waitlisted = True
            registration_error_message = 'Your request to join this event is pending'
        if event.allowed_domains:
            domains = event.allowed_domains.split(',')
            emails = user.get_emails()
            domain_match = [domain for domain in domains if any('@' + domain.strip() in email for email in emails)]
            if not domain_match:
                registration_allowed = False
                registration_error_message = ("To register for the event, your account must be linked with "
                                              f"an email address from the following domains: {domains}. "
                                              "You can add email addresses to your account in the settings menu.")

    if request.method == 'POST':
        if 'confirm_registration' in request.POST.keys():
            event.join_waitlist(user=user, comment_to_applicant='')
            notification.notify_participant_event_waitlist(request=request, user=user, event=event)
            notify_host_cohosts_new_registration(request=request, registered_user=user, event=event)
            messages.success(request, "You have successfully requested to join this event")
            return redirect(event_home)
        elif 'invite_cohost' in request.POST:
            invite_cohost_form = InviteCohostForm(event=event, data=request.POST)
            if invite_cohost_form.is_valid():
                invite_cohost_form.save()
                messages.success(request, "You have successfully invited a cohost")
                target_email = invite_cohost_form.cleaned_data['email']
                notification.cohost_invitation_notify(request, invite_cohost_form,
                                                      target_email)
                messages.success(request, 'An invitation has been sent to: {0}'.format(target_email))
                invite_cohost_form = InviteCohostForm(event=event)
            else:
                messages.error(request, "Submission failed. Please check the form for errors.")
        elif 'cancel_invitation' in request.POST:
            invitation_id = int(request.POST['cancel_invitation'])
            cancel_invitation(request, invitation_id, event)
        elif 'invitation_response' in request.POST.keys():
            host_qs = CohostInvitation.get_user_invitations(user)
            invitation_response_formset = InvitationResponseFormSet(
                request.POST,
                queryset=host_qs,
            )
            if process_invitation_response(request, invitation_response_formset):
                return redirect('event_detail', event_slug=event.slug)
        elif 'confirm_withdraw' in request.POST.keys():
            event_participation_request = EventApplication.objects.filter(
                event=event,
                user=user,
                status=EventApplication.EventApplicationStatus.WAITLISTED)
            if event_participation_request.exists():
                event_participation_request = event_participation_request.first()
                event_participation_request.withdraw(comment_to_applicant='Withdrawn by user')
                notification.notify_participant_event_withdraw(request=request, user=user, event=event)
                messages.success(request, "You have successfully withdrawn your request to join this event. "
                                          "Please submit a new request if you wish to join again.")
                return redirect(event_home)

    event_datasets = event.datasets.filter(is_active=True)
    invitations = CohostInvitation.objects.filter(event=event, is_active=True)
    cohosts = event.participants.filter(is_cohost=True)

    return render(
        request,
        'events/event_detail.html',
        {'event': event,
         'registration_allowed': registration_allowed,
         'registration_error_message': registration_error_message,
         'invite_cohost_form': invite_cohost_form,
         'is_waitlisted': is_waitlisted,
         'event_datasets': event_datasets,
         'invitations': invitations,
         'cohosts': cohosts,
         'invitation_response_formset': invitation_response_formset,
         })
