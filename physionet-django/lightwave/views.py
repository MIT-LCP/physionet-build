from django.shortcuts import render

# Create your views here.
def lightwave_home(request):
    return render(request, 'lightwave/home.html')
