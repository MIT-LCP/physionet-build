from django.contrib import messages
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import os

from .forms import (ProjectCreationForm, metadata_forms, MultiFileFieldForm,
    FolderCreationForm, MoveItemsForm, RenameItemForm, DeleteItemsForm)
from .models import Project, DatabaseMetadata, SoftwareMetadata
from .utility import (get_file_info, get_directory_info, get_storage_info,
    write_uploaded_file, list_items, remove_items, move_items)
from physionet.settings import MEDIA_ROOT, project_file_individual_limit
from user.forms import ProfileForm

import pdb


def download_file(request, file_path):
    """
    Serve a file to download. file_path is the full file path of the file on the server
    """
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
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
        if form.is_valid() and form.cleaned_data['owner'] == user:
            project = form.save()
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



def selected_valid_items(request, selected_items, current_directory):
    """
    Ensure selected files/folders are present in the directory.
    """
    present_items = list_items(current_directory, return_separate=False)
    selected_items = request.POST.getlist('checks')

    if set(selected_items).issubset(present_items):
        if len(selected_items) > 0:
            return True
        else:
            messages.error(request, 'No items were selected.')
    else:
        messages.error(request, 'There was an error with the selected items.')
        return False


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
        # In a subdirectory
        elif os.path.isdir(item_path):
            in_subdir = True
        # Invalid url
        else:
            return Http404()
    # In project's file root
    else:
        in_subdir = False
    
    # The url is not pointing to a file to download.

    # The file directory being examined
    current_directory = os.path.join(project_file_root, sub_item)
    storage_info = get_storage_info(project.storage_allowance*1024**3,
            project.storage_used())

    if request.method == 'POST':
        if 'upload_files' in request.POST:
            upload_files_form = MultiFileFieldForm(project_file_individual_limit,
                storage_info.remaining, current_directory, request.POST, request.FILES)

            if upload_files_form.is_valid():
                files = upload_files_form.files.getlist('file_field')
                for file in files:
                    write_uploaded_file(file=file,
                        write_file_path=os.path.join(current_directory
                    , file.name))
                messages.success(request, 'Your files have been uploaded.')

        elif 'create_folder' in request.POST:
            folder_creation_form = FolderCreationForm(current_directory=current_directory,
                data=request.POST)

            if folder_creation_form.is_valid():
                os.mkdir(os.path.join(current_directory, folder_creation_form.cleaned_data['folder_name']))
                messages.success(request, 'Your folder has been created.')

        elif 'rename_item' in request.POST:
            rename_item_form = RenameItemForm(current_directory, request.POST)
            if rename_item_form.is_valid():
                os.rename(os.path.join(current_directory, rename_item_form.cleaned_data['selected_item']),
                    os.path.join(current_directory, rename_item_form.cleaned_data['new_name']))
                messages.success(request, 'Your item has been renamed.')
            else:
                messages.error(request, rename_item_form.errors)
        
        elif 'move_items' in request.POST:
            move_items_form = MoveItemsForm(current_directory, in_subdir,
                request.POST)
            if move_items_form.is_valid():
                move_items([os.path.join(current_directory, i) for i in move_items_form.cleaned_data['selected_items']],
                    os.path.join(current_directory, move_items_form.cleaned_data['destination_folder']))
                messages.success(request, 'Your items have been moved.')

        elif 'delete_items' in request.POST:
            delete_items_form = DeleteItemsForm(current_directory, request.POST)
            if delete_items_form.is_valid():
                remove_items([os.path.join(current_directory, i) for i in delete_items_form.cleaned_data['selected_items']])
                messages.success(request, 'Your items have been deleted.')

        # Reload the storage info.
        storage_info = get_storage_info(project.storage_allowance*1024**3,
            project.storage_used())

    # Forms
    upload_files_form = MultiFileFieldForm(project_file_individual_limit,
        storage_info.remaining, current_directory)
    folder_creation_form = FolderCreationForm()
    rename_item_form = RenameItemForm(current_directory)
    move_items_form = MoveItemsForm(current_directory, in_subdir)
    delete_items_form = DeleteItemsForm(current_directory)

    # The contents of the directory
    file_names , dir_names = list_items(current_directory)
    display_files = [get_file_info(os.path.join(current_directory, f)) for f in file_names]
    display_dirs = [get_directory_info(os.path.join(current_directory, d)) for d in dir_names]

    return render(request, 'project/project_files.html', {'project':project,
        'display_files':display_files, 'display_dirs':display_dirs,
        'sub_item':sub_item, 'in_subdir':in_subdir, 'storage_info':storage_info,
        'upload_files_form':upload_files_form, 'folder_creation_form':folder_creation_form,
        'rename_item_form':rename_item_form, 'move_items_form':move_items_form,
        'delete_items_form':delete_items_form})


@login_required
def project_collaborators(request, project_id):
    project = Project.objects.get(id=project_id)
    return render(request, 'project/project_collaborators.html', {'project':project})
