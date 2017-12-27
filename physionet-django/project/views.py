from django.contrib import messages
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import os

from .forms import (ProjectCreationForm, metadata_forms, MultiFileFieldForm,
    FolderCreationForm, MoveItemsForm, RenameItemForm, DeleteItemsForm, StorageRequestForm)
from .models import Project, DatabaseMetadata, SoftwareMetadata, StorageRequest
from .utility import (get_file_info, get_directory_info, get_storage_info,
    write_uploaded_file, list_items, remove_items, move_items, get_form_errors)
from physionet.settings import MEDIA_ROOT, project_file_individual_limit
from user.forms import ProfileForm

import pdb


def collaborator_required(base_function):
    """
    Decorator to ensure only collaborators can access projects
    """
    @login_required
    def function_wrapper(request, *args, **kwargs):
        user = request.user
        project = Project.objects.get(id=kwargs['project_id'])
        collaborators = project.collaborators.all()
        if user not in collaborators:
            raise Http404("Unable to access project")
        return base_function(request, *args, **kwargs)
    return function_wrapper


def admin_access(base_function):
    """
    Decorator to allow admins to access any view
    """
    @login_required
    def function_wrapper(request, *args, **kwargs):
        user = request.user
        if user.is_admin:
            return base_function(request, *args, **kwargs)
    return function_wrapper


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

    context = {'projects':projects, 'review_projects':review_projects}
    if user.is_admin:
        storage_requests = StorageRequest.objects.all()
        context['storage_requests'] = storage_requests
    return render(request, 'project/project_home.html', context)


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


@collaborator_required
def project_overview(request, project_id):
    "Overview page of a project"
    project = Project.objects.get(id=project_id)
    
    return render(request, 'project/project_overview.html', {'project':project})


@collaborator_required
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


# Helper functions for project files view

def upload_files(request, upload_files_form):
    if upload_files_form.is_valid():
        files = upload_files_form.files.getlist('file_field')
        for file in files:
            write_uploaded_file(file=file,
                write_file_path=os.path.join(upload_files_form.current_directory
            , file.name))
        messages.success(request, 'Your files have been uploaded.')
    else:
        messages.error(request, get_form_errors(upload_files_form))

def create_folder(request, folder_creation_form):
    if folder_creation_form.is_valid():
        os.mkdir(os.path.join(folder_creation_form.current_directory, folder_creation_form.cleaned_data['folder_name']))
        messages.success(request, 'Your folder has been created.')
    else:
        messages.error(request, get_form_errors(folder_creation_form))

def rename_item(request, rename_item_form):
    if rename_item_form.is_valid():
        os.rename(os.path.join(rename_item_form.current_directory, rename_item_form.cleaned_data['selected_item']),
            os.path.join(rename_item_form.current_directory, rename_item_form.cleaned_data['new_name']))
        messages.success(request, 'Your item has been renamed.')
    else:
        messages.error(request, get_form_errors(rename_item_form))

def move_items(request, move_items_form):
    if move_items_form.is_valid():
        move_items([os.path.join(move_items_form.current_directory, i) for i in move_items_form.cleaned_data['selected_items']],
            os.path.join(move_items_form.current_directory, move_items_form.cleaned_data['destination_folder']))
        messages.success(request, 'Your items have been moved.')
    else:
        messages.error(request, get_form_errors(move_items_form))

def delete_items(request, delete_items_form):
    if delete_items_form.is_valid():
        remove_items([os.path.join(delete_items_form.current_directory, i) for i in delete_items_form.cleaned_data['selected_items']])
        messages.success(request, 'Your items have been deleted.')
    else:
        messages.error(request, get_form_errors(delete_items_form))

@collaborator_required
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
        if 'request_storage' in request.POST:
            storage_request_form = StorageRequestForm(request.POST)
            if storage_request_form.is_valid():
                storage_request_form.save()
                messages.success(request, 'Your storage request has been received.')
            else:
                messages.error(request, get_form_errors(storage_request_form))

        if 'upload_files' in request.POST:
            upload_files_form = MultiFileFieldForm(project_file_individual_limit,
                storage_info.remaining, current_directory, request.POST, request.FILES)
            upload_files(request, upload_files_form)

        elif 'create_folder' in request.POST:
            folder_creation_form = FolderCreationForm(current_directory,
                request.POST)
            create_folder(request, folder_creation_form)

        elif 'rename_item' in request.POST:
            rename_item_form = RenameItemForm(current_directory, request.POST)
            rename_item(request, rename_item_form)
        
        elif 'move_items' in request.POST:
            move_items_form = MoveItemsForm(current_directory, in_subdir,
                request.POST)
            move_items(request, move_items_form)

        elif 'delete_items' in request.POST:
            delete_items_form = DeleteItemsForm(current_directory, request.POST)
            delete_items(request, delete_items_form)

        # Reload the storage info.
        storage_info = get_storage_info(project.storage_allowance*1024**3,
            project.storage_used())

    # Forms
    storage_request = StorageRequest.objects.filter(project=project).first()
    if storage_request:
        storage_request_form = None
    else:
        storage_request_form = StorageRequestForm(initial={'project':project})
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
        'storage_request':storage_request,
        'storage_request_form':storage_request_form,
        'upload_files_form':upload_files_form,
        'folder_creation_form':folder_creation_form,
        'rename_item_form':rename_item_form, 'move_items_form':move_items_form,
        'delete_items_form':delete_items_form})

@collaborator_required
def request_storage(request, project_id):
    """
    Page to request storage
    """
    project = Project.objects.get(id=project_id)
    storage_info = get_storage_info(project.storage_allowance*1024**3,
            project.storage_used())
    if request.method == 'POST':
        storage_request_form = StorageRequestForm(request.POST)


    storage_request_form = StorageRequestForm()

    return render(request, 'project/request_storage.html', 
        {'storage_request_form':storage_request_form})


@collaborator_required
def project_collaborators(request, project_id):
    project = Project.objects.get(id=project_id)
    return render(request, 'project/project_collaborators.html', {'project':project})
