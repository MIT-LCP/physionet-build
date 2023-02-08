from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory


import notification.utility as notification
from events.forms import AddEventForm, EventApplicationResponseForm
from events.models import Event, EventApplication


@login_required
def update_event(request, event_slug, **kwargs):
    user = request.user
    is_instructor = user.has_perm('user.add_event')
    if request.method == 'POST':
        event = Event.objects.get(slug=event_slug)
        event_form = AddEventForm(user=user, data=request.POST, instance=event)
        if event_form.is_valid() and is_instructor:
            event_form.save()
            messages.success(request, "Updated Event Successfully")
        else:
            messages.error(request, event_form.errors)
    else:
        messages.error(request, "Invalid request")
    return redirect(event_home)


@login_required
def get_event_details(request, event_slug):
    is_instructor = request.user.has_perm('user.add_event')
    if not is_instructor:
        return JsonResponse([{'error': 'You don\'t have permission to access event'}], safe=False)
    event = Event.objects.filter(slug=event_slug).values()
    return JsonResponse(list(event), safe=False)


@login_required
def event_home(request):
    """
    List of events
    """
    user = request.user
    is_instructor = user.has_perm('user.add_event')

    EventApplicationResponseFormSet = modelformset_factory(EventApplication,
                                                           form=EventApplicationResponseForm, extra=0)

    # sqlite doesn't support the distinct() method
    events_all = Event.objects.filter(Q(host=user) | Q(participants__user=user))
    events_active = set(events_all.filter(end_date__gte=datetime.now()))
    events_past = set(events_all.filter(end_date__lt=datetime.now()))
    event_form = AddEventForm(user=user)

    url_prefix = notification.get_url_prefix(request)

    form_error = False
    if request.method == 'POST' and 'add-event' in request.POST.keys():
        event_form = AddEventForm(user=user, data=request.POST)
        if event_form.is_valid() and is_instructor:
            event_form.save()
            return redirect(event_home)
        else:
            form_error = True

    # handle notifications to join an event
    if request.method == 'POST' and 'participation_response' in request.POST.keys():

        formset = EventApplicationResponseFormSet(request.POST)
        # only process the form that was submitted
        for form in formset:
            if form.instance.id == int(request.POST['participation_response']):
                if form.is_valid():
                    event_application = form.save(commit=False)
                    if event_application.status == EventApplication.EventApplicationStatus.APPROVED:
                        event_application.accept(comment_to_applicant=form.cleaned_data.get('comment_to_applicant'))
                    elif event_application.status == EventApplication.EventApplicationStatus.NOT_APPROVED:
                        event_application.reject(comment_to_applicant=form.cleaned_data.get('comment_to_applicant'))
                else:
                    messages.error(request, form.errors)
                return redirect(event_home)
        else:
            form_error = True

    # get all participation requests for Active events where the current user is the host and the participants are
    # waiting for a response
    participation_requests = EventApplication.objects.filter(
        status=EventApplication.EventApplicationStatus.WAITLISTED).filter(event__host=user,
                                                                          event__end_date__gte=datetime.now())
    participation_response_formset = EventApplicationResponseFormSet(queryset=participation_requests)
    return render(request, 'events/event_home.html',
                  {'events_active': events_active,
                   'events_past': events_past,
                   'event_form': event_form,
                   'url_prefix': url_prefix,
                   'is_instructor': is_instructor,
                   'form_error': form_error,
                   'participation_response_formset': participation_response_formset,
                   })


@login_required
def event_detail(request, event_slug):
    """
    Detail page of an event
    """
    user = request.user

    event = get_object_or_404(Event, slug=event_slug)

    if event.end_date < datetime.now().date():
        messages.error(request, "This event has now finished")
        return redirect(event_home)

    # host should not be able to add themselves as a participant
    if event.host == user:
        messages.error(request, "You are the host of this event. You cannot add yourself as a participant")
        return redirect(event_home)

    if event.participants.filter(user=user).exists():
        messages.error(request, "Your request to join this event is already accepted")
        return redirect(event_home)

    event_participation_request = EventApplication.objects.filter(event=event, user=user)
    if event_participation_request.exists():
        event_participation_request = event_participation_request.first()
        if event_participation_request.status == EventApplication.EventApplicationStatus.WAITLISTED:
            messages.error(request, "Your request to join this event is already pending")
            return redirect(event_home)

    if event.allowed_domains:
        domains = event.allowed_domains.split(',')
        emails = user.get_emails()
        domain_match = [domain for domain in domains if any('@' + domain.strip() in email for email in emails)]
        if not domain_match:
            messages.error(request, f"To register for the event, your account must be linked with "
                                    f"an email address from the following domains: {domains}. "
                                    f"You can add email addresses to your account in the settings menu.")
            return redirect(event_home)

    if request.method == 'POST':
        if request.POST.get('confirm_event') == 'confirm':
            event.join_waitlist(user=user, comment_to_applicant='')
            messages.success(request, "You have successfully requested to join this event")
            return redirect(event_home)

    return render(request, 'events/event_detail.html', {'event': event})
