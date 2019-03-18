from django.contrib import messages
from django.shortcuts import render

from notification.models import News
import notification.utility as notification
from project.models import License, PublishedProject
from user.forms import ContactForm


def home(request):
    """
    Homepage
    """
    published_projects = PublishedProject.objects.all().order_by('-publish_datetime')[:6]

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)
    news_pieces = News.objects.all().order_by('-publish_datetime')[:5]

    return render(request, 'home.html', {
        'published_projects':published_projects, 'news_pieces':news_pieces,
        'projects_authors_topics':projects_authors_topics})

def author_guidelines(request):
    """
    Insrtuctions for authors
    """
    return render(request, 'about/author_guidelines.html')

def licenses(request):
    """
    Display all licenses
    """
    licenses = {}
    licenses['Database'] = License.objects.filter(resource_type=0).order_by('access_policy')
    licenses['Software'] = License.objects.filter(resource_type=1).order_by('access_policy')
    licenses['Challenge'] = License.objects.filter(resource_type=2).order_by('access_policy')

    return render(request, 'about/licenses.html', {'licenses':licenses})

def license_content(request, license_slug):
    """
    Content for an individual license
    """
    license = License.objects.get(slug=license_slug)
    return render(request, 'about/license_content.html', {'license':license})

def timeline(request):
    """
    Background to PhysioNet as an organization.
    """
    return render(request, 'about/timeline.html')

def about_physionet(request):
    """
    About the site content.
    """
    return render(request, 'about/about_physionet.html')

def faq(request):
    """
    Frequently asked questions
    """
    return render(request, 'about/faq.html')

def contact(request):
    """
    Contact form
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

    return render(request, 'about/contact.html', {'contact_form':contact_form})

def citi_course(request):
    """
    Instructions for completing the CITI training course
    """
    return render(request, 'about/citi_course.html')
