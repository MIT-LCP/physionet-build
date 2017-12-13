from django.shortcuts import render


def home(request):
    return render(request, 'home.html')

# Publish pages

# def submit(request):
#     return render(request, 'submit.html')

def author_guidelines(request):
    return render(request, 'author_guidelines.html')

# About pages

def contact(request):
    return render(request, 'contact.html')

def ourteam(request):
    return render(request, 'ourteam.html')

def funding(request):
    return render(request, 'funding.html')

# Content pages

def data(request):
    return render(request, 'data.html')

def software(request):
    return render(request, 'software.html')

def challenges(request):
    return render(request, 'challenges.html')
