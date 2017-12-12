from django.contrib import messages
from django import forms
from django.forms import modelformset_factory
from django.http import Http404
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .forms import ProjectCreationForm
from .models import metadata_models, Project, DatabaseMetadata, SoftwareMetadata

import pdb
from user.forms import ProfileForm

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

            return redirect('edit_project', project_id=project.id)

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

    # Dynamically generate the metadata modelform for the relevant type
    #MetadataFormset = modelformset_factory(metadata_models[project.resource_type.description],
    MetadataFormset = modelformset_factory(DatabaseMetadata,
        exclude=('slug', 'id'))

    form = MetadataFormset(queryset=DatabaseMetadata.objects.filter(id=project.metadata.id))[0]

    if request.method == 'POST':
        
        formset = MetadataFormset(request.POST)

        # formset = AssociatedEmailFormset(request.POST, instance=user)
        #     set_public_emails(request, formset)

        if formset.is_valid():
            formset.save()
            messages.success(request, 'Your project metadata has been updated.')

    return render(request, 'project/project_metadata.html', {'project':project,
        'form':form, 'messages':messages.get_messages(request)})


@login_required
def project_files(request, project_id):
    project = Project.objects.get(id=project_id)
    return render(request, 'project/project_files.html', {'project':project})


@login_required
def project_collaborators(request, project_id):
    project = Project.objects.get(id=project_id)
    return render(request, 'project/project_collaborators.html', {'project':project})


