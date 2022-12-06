from collections import OrderedDict
from os import path
from re import fullmatch
from urllib.parse import urljoin
from datetime import datetime

import notification.utility as notification
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from notification.models import News
from project.projectfiles import ProjectFiles
from physionet.models import FrontPageButton, Section, StaticPage
from physionet.middleware.maintenance import allow_post_during_maintenance
from project.models import AccessPolicy, DUA, License, ProjectType, PublishedProject
from user.forms import AddEventForm
from user.models import Event


def home(request):
    """
    Homepage
    """
    featured = PublishedProject.objects.filter(featured__isnull=False).order_by('featured')[:6]
    latest = PublishedProject.objects.filter(is_latest_version=True).order_by('-publish_datetime')[:6]
    news_pieces = News.objects.all().order_by('-publish_datetime')[:5]
    front_page_buttons = FrontPageButton.objects.all()
    front_page_banner = News.objects.filter(front_page_banner=True)

    return render(
        request,
        'home.html',
        {
            'featured': featured,
            'latest': latest,
            'news_pieces': news_pieces,
            'front_page_buttons': front_page_buttons,
            'front_page_banner': front_page_banner,
            'is_lightwave_supported': ProjectFiles().is_lightwave_supported(),
        },
    )


def ping(request):
    """
    Healthcheck
    """
    return HttpResponse(status=200)


def license_content(request, license_slug):
    """
    Content for an individual license
    """
    license = get_object_or_404(License, slug=license_slug)

    return render(request, 'about/license_content.html', {'license': license})


def dua_content(request, dua_slug):
    """
    Content for an individual license
    """
    dua = get_object_or_404(DUA, slug=dua_slug)

    return render(request, 'about/dua_content.html', {'dua': dua})


def timeline(request):
    """
    Frequently asked questions
    """
    return render(request, 'about/timeline.html')


def citi_course(request):
    """
    Instructions for completing the CITI training course
    """
    return render(request, 'about/citi_course.html')


def error_404(request, exception=None):
    """
    View for testing the 404 page. To test, uncomment the URL pattern
        in urls.py.
    """
    return render(request, '404.html', {'ERROR_EMAIL': settings.ERROR_EMAIL}, status=404)


def error_403(request, exception=None):
    """
    View for testing the 404 page. To test, uncomment the URL pattern
        in urls.py.
    """
    return render(request, '403.html', {'ERROR_EMAIL': settings.ERROR_EMAIL}, status=403)


def error_500(request, exception=None):
    """
    View for testing the 404 page. To test, uncomment the URL pattern
        in urls.py.
    """
    return render(request, '500.html', {'ERROR_EMAIL': settings.ERROR_EMAIL}, status=500)


def content_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/content_overview.html')


def database_overview(request):
    """
    Temporary content overview
    """
    projects = {}
    for i, policy in AccessPolicy.choices():
        projects[i] = {}
        projects[i]['policy'] = policy
        projects[i]['projects'] = PublishedProject.objects.filter(
            access_policy=i, resource_type=0, is_latest_version=True
        ).order_by(Lower('title'))

    return render(request, 'about/database_index.html',
                  {'projects': projects})


def software_overview(request):
    """
    Temporary content overview
    """
    all_projects = PublishedProject.objects.filter(
        resource_type=1, is_latest_version=True).order_by(Lower('title'))
    return render(request, 'about/software_index.html',
                  {'all_projects': all_projects})


def moody_challenge_overview(request):
    """
    View for detailed information about the George B. Moody PhysioNet Challenge
    """
    return render(request, 'about/moody_challenge_overview_index.html')


def moody_challenge(request):
    """
    View for the list of previous Moody challenges
    """
    moody_challenges = PublishedProject.objects.filter(resource_type=2, is_latest_version=True,
                                                       slug__iregex=r'^challenge-[0-9]{4}$').order_by(
        '-publish_datetime')

    for md_challenge in moody_challenges:
        md_challenge.year = md_challenge.slug.split('-')[1]
        if path.exists(path.join(md_challenge.file_root(), 'sources')):
            md_challenge.sources = True
            if path.exists(path.join(md_challenge.file_root(), 'sources/index.html')):
                md_challenge.sources_index = True
        if path.exists(path.join(md_challenge.file_root(), 'papers/index.html')):
            md_challenge.papers = True

    return render(request, 'about/moody_challenge_index.html', {'moody_challenges': moody_challenges})


def community_challenge(request):
    """
    View for the list of Community challenges
    """
    community_challenges = PublishedProject.objects.filter(resource_type=2, is_latest_version=True,
                                                           slug__iregex=r'^((?!challenge-[0-9]{4}).)*$').order_by(
        '-publish_datetime')

    for c_challenge in community_challenges:
        if path.exists(path.join(c_challenge.file_root(), 'sources')):
            c_challenge.sources = True
            if path.exists(path.join(c_challenge.file_root(), 'sources/index.html')):
                c_challenge.sources_index = True
        if path.exists(path.join(c_challenge.file_root(), 'papers/index.html')):
            c_challenge.papers = True

    return render(request, 'about/community_challenge_index.html', {'community_challenges': community_challenges})


def static_view(request, static_url=None):
    """ Checks for a URL starting with /about/ in StaticPage and
    attempts to render the requested page
    """

    if static_url:
        static_url = urljoin('/about/', static_url + '/')
    else:
        static_url = "/about/"
    static_page = get_object_or_404(StaticPage, url=static_url)

    sections = Section.objects.filter(static_page=static_page)
    params = {'static_page': static_page, 'sections': sections}

    return render(request, 'about/static_template.html', params)


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

    return render(request, 'event_home.html',
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

    return render(request, 'event_participant.html', {'event': event})
