from django.shortcuts import render


def home(request):
    return render(request, 'home.html')

# Publish pages

def author_guidelines(request):
    return render(request, 'author_guidelines.html')

# About pages

def about_physionet(request):
    return render(request, 'about_physionet.html')

def faq(request):
    return render(request, 'faq.html')

def contact(request):
    return render(request, 'contact.html')

def our_team(request):
    return render(request, 'our_team.html')

def funding(request):
    return render(request, 'funding.html')

# Content pages

def data(request):
    return render(request, 'data.html')

def software(request):
    return render(request, 'software.html')

def challenge(request):
    return render(request, 'challenge.html')
