from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory, modelformset_factory, TextInput, CharField
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
import os
import re

from . import forms
from .models import Author, Invitation, Project, PublishedProject, StorageRequest
from .utility import (get_file_info, get_directory_info, get_storage_info,
    write_uploaded_file, list_items, remove_items, move_items as do_move_items,
    get_form_errors, serve_file)
from physionet.settings import MEDIA_ROOT, project_file_individual_limit
from user.forms import ProfileForm
from user.models import User

import pdb


def is_admin(user, *args, **kwargs):
    return user.is_admin

def is_author(user, project):
    authors = project.authors.all()
    return (user in [a.user for a in authors])

def is_invited(user, project):
    "Whether a user has been invited to join a project"
    user_invitations = Invitation.get_user_invitations(user)
    return bool(user_invitations.filter(project=project))


def authorization_required(auth_functions):
    """
    A generic authorization requirement decorator for projects.
    Accepts an iterable of functions, and grants access if any of the
    functions return True.
    """
    def real_decorator(base_function):
        @login_required
        def function_wrapper(request, *args, **kwargs):
            user = request.user
            project = project = Project.objects.get(id=kwargs['project_id'])

            for auth_func in auth_functions:
                if auth_func(user, project):
                    return base_function(request, *args, **kwargs)

            raise Http404("Unable to access page")

        return function_wrapper
    return real_decorator


def get_button_id(post_keys):
    """
    Helper function to extract the submit button label from a form post.
    The button name should be in the form of: "respond-<id>", and there
    should only be one item in the post of that format. This function
    is used to determine which form/button was submitted on a page with
    multiple forms.

    post_keys : keys of a form post.
    """
    button_id = [re.findall('respond-(?P<button_id>\d+)', k) for k in post_keys]
    button_id = [i for i in button_id if i]

    if len(button_id) == 1:
        button_id = int(button_id[0][0])
    else:
        button_id = None

    return button_id


# The version with separate formset and models
@login_required
def project_home(request):
    """
    Home page listing projects a user is involved in:
    - Collaborating projects
    - Reviewing projects
    """
    user = request.user

    projects = Project.objects.filter(authors__in=user.authorships.all())

    # Projects that the user is responsible for reviewing
    review_projects = None

    return render(request, 'project/project_home.html', {'projects':projects,
        'review_projects':review_projects})


def process_invitation_response(request, invitation_response_formset):
    """
    Process an invitation response. Helper function to
    project_invitations
    """
    user = request.user
    invitation_id = get_button_id(request.POST.keys())

    # Only process the form that was submitted
    for invitation_response_form in invitation_response_formset:
        if (invitation_response_form.is_valid() and
                invitation_response_form.cleaned_data['invitation_id'] == invitation_id):
            # Get the specified Invitation and response
            invitation = Invitation.objects.get(id=invitation_id)
            response = int(invitation_response_form.cleaned_data['response'])
            # Update the specified Invitation object, and also any other
            # duplicate invitations (same user, project, and invitation_type)
            emails = user.get_emails()
            invitations = Invitation.objects.filter(email__in=emails,
                project=invitation.project,
                invitation_type=invitation.invitation_type)
            invitations.update(response=response, is_active=False)

            # Carry out the response to the project
            if response:
                response = 'accepted'
                project = invitation.project

                if invitation.invitation_type == 'author':
                    # Create Author object.
                    existing_authors = project.authors.filter(is_human=True)
                    if existing_authors:
                        order = max([a.display_order for a in existing_authors]) + 1
                    else:
                        order = 1
                    Author.objects.create(project=project, user=user,
                        display_order=order)

                elif invitation.invitation_type == 'reviewer':
                    pass
            else:
                project = None
                response = 'rejected'

            messages.success(request, 'You have %s the invitation.' % response)

            return project, response


@login_required
def project_invitations(request):
    """
    Page listing invitations
    """
    user = request.user
    project = None
    invitations = Invitation.get_user_invitations(user)
    author_invitations = invitations.filter(invitation_type='author')
    reviewer_invitations = invitations.filter(invitation_type='reviewer')

    InvitationResponseFormSet = formset_factory(forms.InvitationResponseForm,
        extra=0)
    invitation_response_formset = InvitationResponseFormSet(
        form_kwargs={'user':user},
        initial=[{'invitation_id':inv.id} for inv in invitations])

    if request.method == 'POST':
        invitation_response_formset = InvitationResponseFormSet(
            request.POST, form_kwargs={'user':user})
        project, response = process_invitation_response(request,
            invitation_response_formset)

    return render(request, 'project/project_invitations.html', {
        'invitations':invitations,
        'author_invitations':author_invitations,
        'reviewer_invitations':reviewer_invitations,
        'invitation_response_formset':invitation_response_formset,
        'project':project,})


@login_required
def create_project(request):
    user = request.user

    if request.method == 'POST':
        form = forms.CreateProjectForm(user=user, data=request.POST)
        if form.is_valid():
            project = form.save()
            return redirect('project_overview', project_id=project.id)
    else:
        form = forms.CreateProjectForm(user=user)

    return render(request, 'project/create_project.html', {'form':form})


@authorization_required(auth_functions=(is_admin, is_author, is_invited))
def project_overview(request, project_id):
    "Overview page of a project"
    project = Project.objects.get(id=project_id)

    return render(request, 'project/project_overview.html', {'project':project})


def invite_author(request, invite_author_form):
    """
    Invite a user to be a collaborator
    """
    if invite_author_form.is_valid():
        invite_author_form.save()
        messages.success(request, 'An invitation has been sent to the user')
        return True


def project_authors(request, project_id):
    """
    Page displaying author information and actions.
    """
    user = request.user
    project = Project.objects.get(id=project_id)
    authors = project.authors.all()

    # Initiate the forms
    invite_author_form = forms.InviteAuthorForm(project, user)
    add_author_form = forms.AddAuthorForm(user, project)

    if request.method == 'POST':

        if 'edit_author' in request.POST:
            pass
        if 'invite_author' in request.POST:
            invite_author_form = forms.InviteAuthorForm(project, user, request.POST)
            if invite_author(request, invite_author_form):
                invite_author_form = forms.InviteAuthorForm(project, user)
        elif 'add_author' in request.POST:
            add_author_form = forms.AddAuthorForm(user, project, request.POST)
            if add_author(request, add_author_form):
                add_author_form = forms.AddAuthorForm(user, project)
        elif 'remove_author' in request.POST:
            pass

    invitations = project.invitations.filter(invitation_type='author',
        is_active=True)

    return render(request, 'project/project_authors.html', {'project':project,
        'authors':authors,
        'invitations':invitations, 'invite_author_form':invite_author_form,
        'add_author_form':add_author_form})



def project_metadata(request, project_id):
    project = Project.objects.get(id=project_id)

    form = forms.metadata_forms[project.resource_type](instance=project)

    if request.method == 'POST':
        form = forms.metadata_forms[project.resource_type](request.POST,
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
# The errors need to be explicitly passed into messages because the
# forms are contained in modals and their errors would not be shown

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
        do_move_items([os.path.join(move_items_form.current_directory, i) for i in move_items_form.cleaned_data['selected_items']],
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
            return serve_file(request, item_path)
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
            storage_request_form = forms.StorageRequestForm(request.POST)
            if storage_request_form.is_valid():
                storage_request_form.save()
                messages.success(request, 'Your storage request has been received.')
            else:
                messages.error(request, get_form_errors(storage_request_form))

        if 'upload_files' in request.POST:
            upload_files_form = forms.MultiFileFieldForm(project_file_individual_limit,
                storage_info.remaining, current_directory, request.POST, request.FILES)
            upload_files(request, upload_files_form)

        elif 'create_folder' in request.POST:
            folder_creation_form = forms.FolderCreationForm(current_directory,
                request.POST)
            create_folder(request, folder_creation_form)

        elif 'rename_item' in request.POST:
            rename_item_form = forms.RenameItemForm(current_directory, request.POST)
            rename_item(request, rename_item_form)

        elif 'move_items' in request.POST:
            move_items_form = forms.MoveItemsForm(current_directory, in_subdir,
                request.POST)
            move_items(request, move_items_form)

        elif 'delete_items' in request.POST:
            delete_items_form = forms.DeleteItemsForm(current_directory, request.POST)
            delete_items(request, delete_items_form)

        # Reload the storage info.
        storage_info = get_storage_info(project.storage_allowance*1024**3,
            project.storage_used())

    # Forms
    storage_request = StorageRequest.objects.filter(project=project).first()
    if storage_request:
        storage_request_form = None
    else:
        storage_request_form = forms.StorageRequestForm(initial={'project':project})
    upload_files_form = forms.MultiFileFieldForm(project_file_individual_limit,
        storage_info.remaining, current_directory)
    folder_creation_form = forms.FolderCreationForm()
    rename_item_form = forms.RenameItemForm(current_directory)
    move_items_form = forms.MoveItemsForm(current_directory, in_subdir)
    delete_items_form = forms.DeleteItemsForm(current_directory)

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


def project_submission(request, project_id):
    """
    View submission details regarding a project
    """
    return render(request, 'project/project_submission.html')



def process_storage_request(request, storage_response_formset):
    "Accept or deny a project's storage request"
    # Only process the form that was submitted. Find the relevant project
    matched_project_ids = [re.findall('respond-(?P<project_id>\d+)', k) for k in request.POST.keys()]
    matched_project_ids = [i for i in matched_project_ids if i]

    if len(matched_project_ids) == 1:
        project_id = int(matched_project_ids[0][0])

        for storage_response_form in storage_response_formset:

            if storage_response_form.is_valid():
                if project_id == int(storage_response_form.cleaned_data['project_id']):
                    storage_request = StorageRequest.objects.get(project=project_id)
                    project = storage_request.project
                    if storage_response_form.cleaned_data['response'] == 'Approve':
                        project.storage_allowance = storage_request.request_allowance
                        project.save()
                        messages.success(request, 'The storage request has been approved')
                    else:
                        messages.success(request, 'The storage request has been denied')
                    # Delete the storage request object
                    storage_request.delete()

            #messages.error(request, get_form_errors(storage_response_form))

    else:
        messages.error('Invalid submission')


def storage_requests(request):
    """
    Page listing projects with outstanding storage requests
    """
    user = request.user

    StorageResponseFormSet = formset_factory(forms.StorageResponseForm,
        extra=0)

    if request.method == 'POST':
        storage_response_formset = StorageResponseFormSet(request.POST)
        process_storage_request(request, storage_response_formset)

    storage_requests = StorageRequest.objects.all()
    if storage_requests:
        storage_response_formset = StorageResponseFormSet(
            initial=[{'project_id':sr.project.id} for sr in storage_requests])
    else:
        storage_response_formset = None

    return render(request, 'project/storage_requests.html', {'user':user,
        'storage_requests':storage_requests,
        'storage_response_formset':storage_response_formset})

