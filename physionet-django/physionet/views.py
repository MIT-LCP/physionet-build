from django.shortcuts import render


def home(request):
    return render(request, 'home.html')

# Publish pages

def author_guidelines(request):
    return render(request, 'about/author_guidelines.html')

# About pages

def about_physionet(request):
    return render(request, 'about/about_physionet.html')

def faq(request):
    return render(request, 'about/faq.html')

def contact(request):
    return render(request, 'about/contact.html')

def our_team(request):
    return render(request, 'about/our_team.html')

def funding(request):
    return render(request, 'about/funding.html')

# Content pages

def data(request):
    return render(request, 'data.html')

def software(request):
    return render(request, 'software.html')

def challenge(request):
    return render(request, 'challenge.html')
