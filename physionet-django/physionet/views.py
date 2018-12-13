from django.contrib import messages
from django.shortcuts import render

from notification.models import News
import notification.utility as notification
from project.models import License, PublishedProject
from user.forms import ContactForm

def home(request):
    published_projects = PublishedProject.objects.all().order_by('-publish_datetime')[:8]

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)
    news_pieces = News.objects.all().order_by('-publish_datetime')[:5]

    return render(request, 'home.html', {
        'published_projects':published_projects, 'news_pieces':news_pieces,
        'projects_authors_topics':projects_authors_topics})

# Publish pages

def author_guidelines(request):
    return render(request, 'about/author_guidelines.html')

def licenses(request):
    """
    Display all licenses
    """
    licenses = License.objects.all()
    return render(request, 'about/licenses.html', {'licenses':licenses})

def license_content(request, license_slug):
    """
    Content for an individual license
    """
    license = License.objects.get(slug=license_slug)
    return render(request, 'about/license_content.html', {'license':license})

# About pages

def about_physionet(request):
    return render(request, 'about/about_physionet.html')

def development(request):
    return render(request, 'about/development.html')

def faq(request):
    return render(request, 'about/faq.html')

def contact(request):
    if request.method == 'POST':
        contact_form = ContactForm(request.POST)
        if contact_form.is_valid():
            notification.send_contact_message(contact_form)
            messages.success(request, 'Your message has been received.')
            contact_form = ContactForm()
        else:
            messages.error(request, 'Invalid submission. See form below.')
    else:
        contact_form = ContactForm()

    return render(request, 'about/contact.html', {'contact_form':contact_form})

def citi_instructions(request):
    return render(request, 'about/citi_instructions.html')

# Content pages


def get_content(resource_type=None):
    """
    Helper function to get content shown on a resource listing page
    """
    if resource_type is None:
        published_projects = PublishedProject.objects.all().order_by(
            'publish_datetime')
    else:
        published_projects = PublishedProject.objects.filter(
            resource_type=resource_type).order_by('publish_datetime')

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)

    return projects_authors_topics


def content(request):
    """
    List of all published resources
    """
    projects_authors_topics = get_content()
    return render(request, 'content_list.html', {'content_name':'Content',
        'projects_authors_topics':projects_authors_topics})


def data(request):
    """
    List of published databases
    """
    projects_authors_topics = get_content(resource_type=0)
    return render(request, 'content_list.html', {'content_name':'Databases',
        'projects_authors_topics':projects_authors_topics})


def software(request):
    """
    List of published software projects
    """
    projects_authors_topics = get_content(resource_type=1)
    return render(request, 'content_list.html', {'content_name':'Software',
        'projects_authors_topics':projects_authors_topics})
