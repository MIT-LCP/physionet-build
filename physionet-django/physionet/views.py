from collections import OrderedDict
from os import path
from re import fullmatch

import notification.utility as notification
from django.contrib import messages
from django.conf import settings
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse
from django.shortcuts import render, get_object_or_404
from notification.models import News
from project.projectfiles import ProjectFiles
from physionet.models import Section, StaticPage
from physionet.middleware.maintenance import allow_post_during_maintenance
from project.models import AccessPolicy, License, ProjectType, PublishedProject
from user.forms import ContactForm


def home(request):
    """
    Homepage
    """
    featured = PublishedProject.objects.filter(featured__isnull=False).order_by('featured')[:6]
    latest = PublishedProject.objects.filter(is_latest_version=True).order_by('-publish_datetime')[:6]
    news_pieces = News.objects.all().order_by('-publish_datetime')[:5]
    front_page_banner = News.objects.filter(front_page_banner=True)

    return render(
        request,
        'home.html',
        {
            'featured': featured,
            'latest': latest,
            'news_pieces': news_pieces,
            'front_page_banner': front_page_banner,
            'is_lightwave_supported': ProjectFiles().is_lightwave_supported(),
        },
    )


def ping(request):
    """
    Healthcheck
    """
    return HttpResponse(status=200)


# def about_publish(request):
#     """
#     Instructions for authors
#     """
#     licenses = OrderedDict()
#     descriptions = OrderedDict()
#     for resource_type in ProjectType.objects.all():
#         descriptions[resource_type.name] = resource_type.description
#         licenses[resource_type.name] = License.objects.filter(resource_types__contains=str(resource_type.id)).order_by(
#             'access_policy'
#         )
#
#     static_page = get_object_or_404(StaticPage, url="share")
#     sections = Section.objects.filter(static_page=static_page)
#
#     return render(
#         request, 'about/publish.html', {'licenses': licenses, 'descriptions': descriptions, 'sections': sections}
#     )


def license_content(request, license_slug):
    """
    Content for an individual license
    """
    try:
        license = License.objects.get(slug=license_slug)
    except License.DoesNotExist:
        raise Http404()

    return render(request, 'about/license_content.html', {'license': license})


# @allow_post_during_maintenance
# def about(request):
#     """
#     About the site content.
#     """
#     if request.method == 'POST':
#         contact_form = ContactForm(request.POST)
#         if contact_form.is_valid():
#             notification.send_contact_message(contact_form)
#             messages.success(request, 'Your message has been sent.')
#             contact_form = ContactForm()
#         else:
#             messages.error(request, 'Invalid submission. See form below.')
#     else:
#         contact_form = ContactForm()
#
#     static_page = get_object_or_404(StaticPage, url="about")
#     sections = Section.objects.filter(static_page=static_page)
#
#     return render(request, 'about/about.html', {'contact_form': contact_form, 'sections': sections})


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


def challenge_overview(request):
    """
    Temporary content overview
    """
    all_challenges = PublishedProject.objects.filter(resource_type=2,
        is_latest_version=True).order_by('-publish_datetime')

    for challenge in all_challenges:
        if fullmatch(r'challenge-[0-9]{4}$', challenge.slug):
            challenge.year = challenge.slug.split('-')[1]
        if path.exists(path.join(challenge.file_root() , 'sources')):
            challenge.sources = True
            if path.exists(path.join(challenge.file_root() , 'sources/index.html')):
                challenge.sources_index = True
        if path.exists(path.join(challenge.file_root() , 'papers/index.html')):
            challenge.papers = True

    return render(request, 'about/challenge_index.html',
        {'all_challenges': all_challenges})


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


def static_view(request, static_url='about'):
    """
    accepts URL from StaticPage and renders the page
    """

    # breakpoint()
    static_page = get_object_or_404(StaticPage, url=static_url)
    # CHECK TO SEE IF CAN ACCESS sections VIA static_page:
    sections = Section.objects.filter(static_page=static_page)

    parameters = {'static_page': static_page, 'sections': sections}

    # get extra parameters for pages as needed
    if static_url == 'about':
        if request.method == 'POST':
            contact_form = ContactForm(request.POST)
            if contact_form.is_valid():
                notification.send_contact_message(contact_form)
                messages.success(request, 'Your message has been sent.')
                contact_form = ContactForm()
            else:
                messages.error(request, 'Invalid submission. See form below.')
        else:
            contact_form = ContactForm()

        parameters['contact_form'] = contact_form

        # return render(
        #     request, 'about/static_template.html', {'contact_form': contact_form, 'static_page': static_page,
        #                                             'sections': sections}
        # )
    elif static_url == 'publish':
        licenses = OrderedDict()
        descriptions = OrderedDict()
        for resource_type in ProjectType.objects.all():
            descriptions[resource_type.name] = resource_type.description
            licenses[resource_type.name] = License.objects.filter(
                resource_types__contains=str(resource_type.id)).order_by(
                'access_policy'
            )

        parameters['licenses'] = licenses
        parameters['descriptions'] = descriptions

        # return render(
        #     request, 'about/static_template.html', {'licenses': licenses, 'descriptions': descriptions,
        #                                             'static_page': static_page, 'sections': sections}
        # )
    # else:
    #     return render(
    #         request, 'about/static_template.html', {'static_page': static_page, 'sections': sections}

    return render(
        request, 'about/static_template.html', parameters
    )

def tutorial_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/tutorial_index.html')
