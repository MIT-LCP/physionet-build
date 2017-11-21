from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from .forms import ProjectCreationForm

@login_required
def create_project(request):
    form = ProjectCreationForm()
    return render(request, 'project/create_project.html', {'form':form})
