from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .forms import ProjectCreationForm
from .models import Project

import pdb


@login_required
def project_home(request):
    """
    Home page listing projects
    """
    user = request.user

    projects = Project.objects.filter(owner=user)

    return render(request, 'project/project_home.html', {'projects':projects})




@login_required
def create_project(request):
    user = request.user
    form = ProjectCreationForm(initial={'owner':user})

    if request.method == 'POST':
        form = ProjectCreationForm(request.POST)
        if form.is_valid():
            print('\n\nvalid!')
            project = form.save(owner=user)

            return render(request, 'project/create_project_done.html', {'email':user.email})

            return redirect('edit_project')

    return render(request, 'project/create_project.html', {'form':form})


@login_required
def edit_project(request):
    return redirect('project_metadata')

@login_required
def project_metadata(request):
    project = Project.objects.get(slug=slug, owner=request.user)

@login_required
def project_files(request):
    project = Project.objects.get(slug=slug, owner=request.user)

@login_required
def project_collaborators(request):
    project = Project.objects.get(slug=slug, owner=request.user)