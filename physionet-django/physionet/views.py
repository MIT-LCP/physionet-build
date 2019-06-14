from collections import OrderedDict

from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect
from django.contrib.contenttypes.models import ContentType

from notification.models import News
import notification.utility as notification
from project.models import (License, PublishedProject, Author, ActiveProject,
                            Metadata)
from user.forms import ContactForm
from project import forms


def home(request):
    """
    Homepage
    """
    featured = PublishedProject.objects.filter(featured=True).order_by('-publish_datetime')[:6]
    latest = PublishedProject.objects.all().order_by('-publish_datetime')[:6]
    news_pieces = News.objects.all().order_by('-publish_datetime')[:5]

    return render(request, 'home.html', {'featured': featured,
                                         'latest': latest,
                                         'news_pieces': news_pieces})


def about_publish(request):
    """
    Instructions for authors
    """
    licenses = OrderedDict()
    for resource_type, resource_label in Metadata.RESOURCE_TYPES:
        licenses[resource_label] = License.objects.filter(
            resource_types__contains=str(resource_type)).order_by('access_policy')

    return render(request, 'about/publish.html', {'licenses': licenses})


def license_content(request, license_slug):
    """
    Content for an individual license
    """
    try:
        license = License.objects.get(slug=license_slug)
    except License.DoesNotExist:
        raise Http404()

    return render(request, 'about/license_content.html', {'license': license})


def about(request):
    """
    About the site content.
    """
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

    return render(request, 'about/about.html', {'contact_form': contact_form})


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
    return render(request,'404.html', status=404)


def error_403(request, exception=None):
    """
    View for testing the 404 page. To test, uncomment the URL pattern
        in urls.py.
    """
    return render(request,'403.html', status=403)


def error_500(request, exception=None):
    """
    View for testing the 404 page. To test, uncomment the URL pattern
        in urls.py.
    """
    return render(request, "500.html", status=500)


def content_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/content_overview.html')


def database_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/database_index.html')


def software_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/software_index.html')


def challenge_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/challenge_index.html')


def tutorial_overview(request):
    """
    Temporary content overview
    """
    return render(request, 'about/tutorial_index.html')
