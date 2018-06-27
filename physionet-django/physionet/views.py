from django.shortcuts import render

from project.models import DataUseAgreement, License


def home(request):
    return render(request, 'home.html')

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
