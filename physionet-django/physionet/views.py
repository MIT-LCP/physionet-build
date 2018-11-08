from django.shortcuts import render

from notification.models import News
from project.models import DataUseAgreement, License, PublishedProject


def home(request):
    published_projects = PublishedProject.objects.all().order_by('-publish_datetime')[:8]

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)
    news_pieces = News.objects.all().order_by('-datetime')[:5]

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

def duas(request):
    duas = DataUseAgreement.objects.all()
    return render(request, 'about/duas.html', {'duas':duas})

def dua_content(request, dua_slug):
    dua = DataUseAgreement.objects.get(slug=dua_slug)
    return render(request, 'about/dua_content.html', {'dua':dua})


# About pages

def about_physionet(request):
    return render(request, 'about/about_physionet.html')

def development(request):
    return render(request, 'about/development.html')

def faq(request):
    return render(request, 'about/faq.html')

def contact(request):
    return render(request, 'about/contact.html')


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




