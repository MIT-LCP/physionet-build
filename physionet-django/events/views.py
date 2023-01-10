from datetime import datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required

import notification.utility as notification
from events.forms import AddEventForm
from user.models import Event


@login_required
def event_home(request):
    """
    List of events
    """
    user = request.user
    is_instructor = user.has_perm('user.add_event')

    # sqlite doesn't support the distinct() method
    events_all = Event.objects.filter(Q(host=user) | Q(participants__user=user))
    events_active = set(events_all.filter(end_date__gte=datetime.now()))
    events_past = set(events_all.filter(end_date__lt=datetime.now()))
    event_form = AddEventForm(user=user)

    url_prefix = notification.get_url_prefix(request)

    form_error = False
    if request.method == 'POST':
        event_form = AddEventForm(user=user, data=request.POST)
        if event_form.is_valid() and is_instructor:
            event_form.save()
            return redirect(event_home)
        else:
            form_error = True

    return render(request, 'events/event_home.html',
                  {'events_active': events_active,
                   'events_past': events_past,
                   'event_form': event_form,
                   'url_prefix': url_prefix,
                   'is_instructor': is_instructor,
                   'form_error': form_error
                   })


@login_required
def event_add_participant(request, event_slug):
    """
    Adds participants to an event.
    """
    user = request.user

    event = get_object_or_404(Event, slug=event_slug)

    if event.end_date < datetime.now().date():
        messages.error(request, "This event has now finished")
        return redirect(event_home)

    if event.participants.filter(user=user).exists():
        messages.success(request, "You are already enrolled")
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
            event.enroll_user(user)
            messages.success(request, "You have been enrolled")
            return redirect(event_home)

    return render(request, 'events/event_participant.html', {'event': event})
