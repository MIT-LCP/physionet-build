from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.contenttypes.models import ContentType

from notification.models import News
import notification.utility as notification
from project.models import License, PublishedProject, Author, ActiveProject
from user.forms import ContactForm
from project import forms


def home(request):
    """
    Homepage
    """
    published_projects = PublishedProject.objects.all().order_by('-publish_datetime')[:6]
    news_pieces = News.objects.all().order_by('-publish_datetime')[:5]

    return render(request, 'home.html', {
        'projects':published_projects, 'news_pieces':news_pieces})

def about_publish(request):
    """
    Insrtuctions for authors
    """
    licenses = {}
    licenses['Database'] = License.objects.filter(resource_type=0).order_by('access_policy')
    licenses['Software'] = License.objects.filter(resource_type=1).order_by('access_policy')
    licenses['Challenge'] = License.objects.filter(resource_type=2).order_by('access_policy')

    user = request.user

    if user.is_authenticated:
        n_submitting = Author.objects.filter(user=user, is_submitting=True,
            content_type=ContentType.objects.get_for_model(ActiveProject)).count()
        if n_submitting >= ActiveProject.MAX_SUBMITTING_PROJECTS:
            return render(request, 'project/project_limit_reached.html',
                {'max_projects':ActiveProject.MAX_SUBMITTING_PROJECTS})

        if request.method == 'POST':
            form = forms.CreateProjectForm(user=user, data=request.POST)
            if form.is_valid():
                project = form.save()
                return redirect('project_overview', project_slug=project.slug)
        else:
            form = forms.CreateProjectForm(user=user)
    else:
        form = ''

    return render(request, 'about/publish.html', {'licenses':licenses, 'form':form})

def license_content(request, license_slug):
    """
    Content for an individual license
    """
    license = License.objects.get(slug=license_slug)
    return render(request, 'about/license_content.html', {'license':license})

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

    return render(request, 'about/about.html', {'contact_form':contact_form})

def timeline(request):
    """
    Background to PhysioNet as an organization.
    """
    return render(request, 'about/timeline.html')

def faq(request):
    """
    Frequently asked questions
    """
    return render(request, 'about/faq.html')

def citi_course(request):
    """
    Instructions for completing the CITI training course
    """
    return render(request, 'about/citi_course.html')
