from django.shortcuts import render

from project.models import License


def home(request):
    return render(request, 'home.html')

# Publish pages

def author_guidelines(request):
    return render(request, 'about/author_guidelines.html')

def licenses(request):
    licenses = License.objects.all()
    return render(request, 'about/licenses.html', {'licenses':licenses})

def full_license(request, license_slug):
    license = License.objects.get(slug=license_slug)
    return render(request, 'about/full_license.html', {'license':license})


# About pages

def about_physionet(request):
    return render(request, 'about/about_physionet.html')

def faq(request):
    return render(request, 'about/faq.html')

def contact(request):
    return render(request, 'about/contact.html')


# Content pages

def data(request):
    return render(request, 'data.html')

def software(request):
    return render(request, 'software.html')

def challenge(request):
    return render(request, 'challenge.html')
