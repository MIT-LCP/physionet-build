from django.shortcuts import render


def console_home(request):
    return render(request, 'console/console_home.html')
