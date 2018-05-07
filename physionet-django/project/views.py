import os
import pdb
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.forms import formset_factory, inlineformset_factory, modelformset_factory, Textarea, Select
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.utils import timezone

from . import forms
from .models import (Affiliation, Author, Invitation, Project,
    PublishedProject, StorageRequest, PROJECT_FILE_SIZE_LIMIT)
from .utility import (get_file_info, get_directory_info, get_storage_info,
    write_uploaded_file, list_items, remove_items, move_items as do_move_items,
    get_form_errors, serve_file)
from user.forms import ProfileForm
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

RESPONSE_ACTIONS = {0:'rejected', 1:'accepted'}


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
            project = Project.objects.get(id=kwargs['project_id'])

            for auth_func in auth_functions:
                if auth_func(user, project):
                    return base_function(request, *args, **kwargs)

            raise Http404("Unable to access page")

        return function_wrapper
    return real_decorator


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
    Process an invitation response.
    Helper function to project_invitations
    """
    user = request.user
    invitation_id = int(request.POST['invitation_response'])
    for invitation_response_form in invitation_response_formset:
        # Only process the response that was submitted
        if invitation_response_form.instance.id == invitation_id:
            if invitation_response_form.is_valid() and invitation_response_form.instance.email in user.get_emails():
                # Update this invitation, and any other one made to the
                # same user, project, and invitation type
                invitation = invitation_response_form.save(commit=False)
                project = invitation.project
                invitations = Invitation.objects.filter(is_active=True,
                    email__in=user.get_emails(), project=project,
                    invitation_type=invitation.invitation_type)
                invitations.update(response=invitation.response,
                    response_message=invitation.response_message,
                    response_datetime=timezone.now(), is_active=False)
                # Create a new Author object
                if invitation.response:
                    Author.objects.create(project=project, user=user,
                        display_order=project.authors.count() + 1)

                messages.success(request, 'The invitation has been %s.' % RESPONSE_ACTIONS[invitation.response])

@login_required
def project_invitations(request):
    """
    Page for listing and responding to project invitations
    """
    user = request.user

    InvitationResponseFormSet = modelformset_factory(Invitation,
        fields=('response', 'response_message'),
        widgets={'response':Select(choices=RESPONSE_CHOICES),
                 'response_message':Textarea()}, extra=0)

    if request.method == 'POST':
        invitation_response_formset = InvitationResponseFormSet(request.POST)
        process_invitation_response(request, invitation_response_formset)

    invitation_response_formset = InvitationResponseFormSet(
        queryset=Invitation.get_user_invitations(user,
        invitation_types=['author']))

    return render(request, 'project/project_invitations.html', {
        'invitation_response_formset':invitation_response_formset})


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
    """
    Overview page of a project
    """
    project = Project.objects.get(id=project_id)

    return render(request, 'project/project_overview.html', {'project':project})


def edit_affiliations(request, affiliation_formset):
    """
    Edit affiliation information
    Helper function for `project_authors`.
    """
    if affiliation_formset.is_valid():
        affiliation_formset.save()
        messages.success(request, 'Your author affiliations have been updated')
        return True
    else:
        messages.error(request, 'Submission unsuccessful. See form for errors.')

def order_authors(request, order_formset):
    """
    Order authors of a project
    Helper function for `project_authors`.
    """
    if order_formset.is_valid():
        order_formset.save()
        messages.success(request, 'The author display order has been udpated')
        return True
    else:
        messages.error(request, 'Submission unsuccessful. See form for errors.')

def invite_author(request, invite_author_form):
    """
    Invite a user to be a collaborator.
    Helper function for `project_authors`.
    """
    if invite_author_form.is_valid():
        invite_author_form.save()
        messages.success(request, 'An invitation has been sent to the user')
        return True
    else:
        messages.error(request, 'Submission unsuccessful. See form for errors.')

def add_author(request, add_author_form):
    """
    Add an organizational author
    """
    if add_author_form.is_valid():
        add_author_form.save()
        messages.success(request, 'The organizational author has been added')
        return True
    else:
        messages.error(request, 'Submission unsuccessful. See form for errors.')

def remove_author(request, remove_author_form):
    """
    Remove an author from a project
    Helper function for `project_authors`.
    """
    if remove_author_form.is_valid():
        author = remove_author_form.cleaned_data['author']
        author.delete()
        messages.success(request, 'The author has been removed from the project')
        return True
    else:
        messages.error(request, 'Submission unsuccessful. See form for errors.')

def cancel_invitation(request, cancel_invitation_form):
    """
    Cancel an author invitation for a project.
    Helper function for `project_authors`.
    """
    if cancel_invitation_form.is_valid():
        invitation = cancel_invitation_form.cleaned_data['invitation']
        invitation.is_active = False
        invitation.save()
        messages.success(request, 'The invitation has been cancelled')
        return True
    else:
        messages.error(request, 'Submission unsuccessful. See form for errors.')

@authorization_required(auth_functions=(is_admin, is_author))
def project_authors(request, project_id):
    """
    Page displaying author information and actions.
    """
    user = request.user
    project = Project.objects.get(id=project_id)
    authors = project.authors.all().order_by('display_order')
    author = authors.get(user=user)
    affiliations = author.affiliations.all()

    # Formset factories
    AffiliationFormSet = generic_inlineformset_factory(Affiliation,
        fields=('name',), extra=3, max_num=3)
    OrderFormSet = inlineformset_factory(Project, Author,
        formset=forms.AuthorOrderFormSet,
        fields=('display_order',),
        can_delete=False, extra=0)

    # Initiate the forms
    edit_author_form = forms.AuthorForm(instance=author)
    affiliation_formset = AffiliationFormSet(instance=author)
    order_formset = OrderFormSet(instance=project)
    invite_author_form = forms.InviteAuthorForm(project, user)
    add_author_form = forms.AddAuthorForm(user=user, project=project)
    remove_author_form = forms.AuthorChoiceForm(user=user, project=project)
    cancel_invitation_form = forms.InvitationChoiceForm(user=user, project=project)

    if request.method == 'POST':
        if 'edit_author' in request.POST:
            edit_author_form = forms.AuthorForm(instance=author,
                data=request.POST)
            if edit_author_form.is_valid():
                edit_author_form.save()
                messages.success(request,
                    'Your author information has been updated')
        elif 'edit_affiliations' in request.POST:
            affiliation_formset = AffiliationFormSet(instance=author,
                data=request.POST)
            if edit_affiliations(request, affiliation_formset):
                affiliation_formset = AffiliationFormSet(
                    instance=author)
        elif 'order_authors' in request.POST:
            order_formset = OrderFormSet(instance=project, data=request.POST)
            if order_authors(request, order_formset):
                order_formset = OrderFormSet(instance=project)
        if 'invite_author' in request.POST:
            invite_author_form = forms.InviteAuthorForm(project, user, request.POST)
            if invite_author(request, invite_author_form):
                invite_author_form = forms.InviteAuthorForm(project, user)
        elif 'add_author' in request.POST:
            add_author_form = forms.AddAuthorForm(user, project, request.POST)
            if add_author(request, add_author_form):
                add_author_form = forms.AddAuthorForm(user, project)
        elif 'remove_author' in request.POST:
            remove_author_form = forms.AuthorChoiceForm(user=user,
                project=project, data=request.POST)
            if remove_author(request, remove_author_form):
                remove_author_form = forms.AuthorChoiceForm(user=user,
                    project=project)
        elif 'cancel_invitation' in request.POST:
            cancel_invitation_form = forms.InvitationChoiceForm(user=user,
                project=project, data=request.POST)
            if cancel_invitation(request, cancel_invitation_form):
                cancel_invitation_form = forms.InvitationChoiceForm(user=user,
                    project=project)

    invitations = project.invitations.filter(invitation_type='author',
        is_active=True)

    return render(request, 'project/project_authors.html', {'project':project,
        'authors':authors, 'invitations':invitations,
        'edit_author_form':edit_author_form,
        'affiliation_formset':affiliation_formset,
        'order_formset':order_formset,
        'invite_author_form':invite_author_form,
        'add_author_form':add_author_form,
        'remove_author_form':remove_author_form,
        'cancel_invitation_form':cancel_invitation_form})


@authorization_required(auth_functions=(is_admin, is_author))
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

@authorization_required(auth_functions=(is_admin, is_author))
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
            upload_files_form = forms.MultiFileFieldForm(PROJECT_FILE_SIZE_LIMIT,
                storage_info.remaining, current_directory, request.POST,
                request.FILES)
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
    upload_files_form = forms.MultiFileFieldForm(PROJECT_FILE_SIZE_LIMIT,
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


@authorization_required(auth_functions=(is_admin, is_author))
def project_preview(request, project_id):
    """
    Preview what the published project would look like
    """
    user = request.user
    project = Project.objects.get(id=project_id)

    return render(request, 'project/project_submission.html', {'user':user,
        'project':project})


@authorization_required(auth_functions=(is_admin, is_author))
def project_submission(request, project_id):
    """
    View submission details regarding a project
    """
    user = request.user
    project = Project.objects.get(id=project_id)

    return render(request, 'project/project_submission.html', {'user':user,
        'project':project})


def process_storage_response(request, storage_response_formset):
    user = request.user
    storage_request_id = int(request.POST['storage_response'])

    for storage_response_form in storage_response_formset:
        # Only process the response that was submitted
        if storage_response_form.instance.id == storage_request_id:
            if storage_response_form.is_valid():
                storage_request = storage_response_form.save(commit=False)
                storage_request.responder = request.user
                storage_request.response_datetime = timezone.now()
                storage_request.is_active = False
                storage_request.save()
                project = storage_request.project
                if storage_request.response:
                    project.storage_allowance = storage_request.request_allowance
                    project.save()
                messages.success(request, 'The storage request has been %s.' % RESPONSE_ACTIONS[storage_request.response])

@login_required
@user_passes_test(is_admin)
def storage_requests(request):
    """
    Page for listing and responding to project storage requests
    """
    user = request.user

    StorageResponseFormSet = modelformset_factory(StorageRequest,
        fields=('response', 'response_message'),
        widgets={'response':Select(choices=RESPONSE_CHOICES),
                 'response_message':Textarea()}, extra=0)

    if request.method == 'POST':
        storage_response_formset = StorageResponseFormSet(request.POST)
        process_storage_response(request, storage_response_formset)

    storage_response_formset = StorageResponseFormSet(
        queryset=StorageRequest.objects.filter(is_active=True))

    return render(request, 'project/storage_requests.html', {'user':user,
        'storage_response_formset':storage_response_formset})
