from django.contrib import messages
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import os

from .forms import ProjectCreationForm, metadata_forms
from .models import Project, DatabaseMetadata, SoftwareMetadata
from .utility import get_file_info, get_directory_info
from physionet.settings import MEDIA_ROOT

import pdb
from user.forms import ProfileForm


def download_file(request, file_path):
    """
    Serve a file to download. file_path is the full file path of the file on the server
    """
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            response = HttpResponse(f.read())
            response['Content-Disposition'] = 'attachment; filename=' + os.path.basename(file_path)
            return response
    else:
        return Http404()

@login_required
def project_home(request):
    "Home page listing projects a user is involved in"
    
    user = request.user
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

            return redirect('project_overview', project_id=project.id)

    return render(request, 'project/create_project.html', {'form':form})


@login_required
def project_overview(request, project_id):
    "Overview page of a project"
    user = request.user

    # Only allow access if the user is a collaborator
    # Turn this into a decorator, with login decorator
    project = Project.objects.get(id=project_id)
    collaborators = project.collaborators.all()
    if user not in collaborators:
        raise Http404("Unable to access project")

    return render(request, 'project/project_overview.html', {'project':project})


@login_required
def project_metadata(request, project_id):
    project = Project.objects.get(id=project_id)

    form = metadata_forms[project.resource_type.description](instance=project)

    if request.method == 'POST':
        form = metadata_forms[project.resource_type.description](request.POST,
            instance=project)

        if form.is_valid():
            form.save()
            messages.success(request, 'Your project metadata has been updated.')
        else:
            messages.error(request,
                'There was an error with the information entered, please verify and try again.')

    return render(request, 'project/project_metadata.html', {'project':project,
        'form':form, 'messages':messages.get_messages(request)})


@login_required
def project_files(request, project_id, sub_item=''):
    "View and manipulate files in a project"
    project = Project.objects.get(id=project_id)

    # Directory where files are kept for the project
    project_file_root = project.file_root()

    # Case of accessing a file or subdirectory
    if sub_item:
        item_path = os.path.join(project_file_root, sub_item)
        # Serve a file
        if os.path.isfile(item_path):
            return download_file(request, item_path)
        # Invalid url
        elif not os.path.isdir(item_path):
            return Http404()

    # The url is not pointing to a file. Present the directory.
    file_dir = os.path.join(project_file_dir, sub_item)

    file_names = sorted([f for f in os.listdir(file_dir) if os.path.isfile(os.path.join(file_dir, f)) and not f.endswith('~')])
    dir_names = sorted([d for d in os.listdir(file_dir) if os.path.isdir(os.path.join(file_dir, d))])

    display_files = [get_file_info(os.path.join(file_dir, f)) for f in file_names]
    display_dirs = [get_directory_info(os.path.join(file_dir, d)) for d in dir_names]

    return render(request, 'project/project_files.html', {'project':project,
        'display_files':display_files, 'display_dirs':display_dirs, 'sub_item':sub_item})


@login_required
def project_collaborators(request, project_id):
    project = Project.objects.get(id=project_id)
    return render(request, 'project/project_collaborators.html', {'project':project})

