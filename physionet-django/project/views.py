from django.http import Http404
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

    # Projects that the user is collaborating in
    projects = Project.objects.filter(collaborators__in=[user])

    # Projects that the user is responsible for reviewing
    review_projects = None
    return render(request, 'project/project_home.html', {'projects':projects,
        'review_projects':review_projects})


@login_required
def create_project(request):
    user = request.user
    form = ProjectCreationForm(initial={'owner':user})

    if request.method == 'POST':
        form = ProjectCreationForm(request.POST)
        if form.is_valid():
            print('\n\nvalid!')
            project = form.save(owner=user)

            return redirect('edit_project', project_id=project.id)

    return render(request, 'project/create_project.html', {'form':form})


@login_required
def edit_project(request, project_id):
    user = request.user

    # Only allow access if the user is a collaborator
    # Turn this into a decorator, with login decorator
    project = Project.objects.get(id=project_id)
    collaborators = project.collaborators.all()
    if user not in collaborators:
        raise Http404("Unable to access project")

    return redirect('project_metadata', project_id=project_id)



@login_required
def project_metadata(request, project_id):
    project = Project.objects.get(id=project_id)


@login_required
def project_files(request, project_id):
    project = Project.objects.get(id=project_id)

@login_required
def project_collaborators(request, project_id):
    project = Project.objects.get(id=project_id)