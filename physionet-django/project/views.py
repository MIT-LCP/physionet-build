import os
import pdb
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import formset_factory, inlineformset_factory, modelformset_factory, Textarea, Select
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.template import loader
from django.utils import timezone

from . import forms
from .models import (Affiliation, Author, Invitation, Project,
    PublishedProject, StorageRequest, PROJECT_FILE_SIZE_LIMIT, Reference,
    Topic, Contact, Publication)
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

def is_submitting_author(user, project):
    return user == project.submitting_author

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
                invitation = invitation_response_form.instance
                project = invitation.project
                invitations = Invitation.objects.filter(is_active=True,
                    email__in=user.get_emails(), project=project,
                    invitation_type=invitation.invitation_type)
                affected_emails = [i.email for i in invitations]
                invitations.update(response=invitation.response,
                    response_message=invitation.response_message,
                    response_datetime=timezone.now(), is_active=False)
                # Create a new Author object
                if invitation.response:
                    Author.objects.create(project=project, user=user,
                        display_order=project.authors.count() + 1)
                # Send an email notifying the submitting author
                target_email = project.submitting_author.email
                subject = "PhysioNet Project Authorship Response"
                context = {'project_title':project.title,
                           'response':RESPONSE_ACTIONS[invitation.response],
                           'domain':get_current_site(request)}

                for email in affected_emails:
                    context['author_email'] = email
                    body = loader.render_to_string('project/email/author_response.html', context)
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                        [target_email], fail_silently=False)

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


@authorization_required(auth_functions=(is_author, is_invited))
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


def invite_author(request, invite_author_form):
    """
    Invite a user to be a collaborator.
    Helper function for `project_authors`.
    """
    if invite_author_form.is_valid():
        invite_author_form.save()
        inviter = invite_author_form.inviter
        target_email = invite_author_form.cleaned_data['email']

        subject = "PhysioNet Project Authorship Invitation"
        context = {'inviter_name':inviter.get_full_name(),
                   'inviter_email':inviter.email,
                   'project_title':invite_author_form.project.title,
                   'domain':get_current_site(request)}
        body = loader.render_to_string('project/email/invite_author.html', context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
            [target_email], fail_silently=False)
        messages.success(request, 'An invitation has been sent to the email')
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

def remove_author(request, author_id):
    """
    Remove an author from a project
    Helper function for `project_authors`.
    """
    user = request.user
    author = Author.objects.get(id=author_id)

    if author.project.submitting_author == user:
        # Other author orders may have to be decreased when this author
        # is removed
        higher_authors = author.project.authors.filter(display_order__gt=author.display_order)
        author.delete()
        if higher_authors:
            for author in higher_authors:
                author.display_order -= 1
                author.save()
        messages.success(request, 'The author has been removed from the project')
        return True

def cancel_invitation(request, invitation_id):
    """
    Cancel an author invitation for a project.
    Helper function for `project_authors`.
    """
    user = request.user
    invitation = Invitation.objects.get(id=invitation_id)
    if invitation.project.submitting_author == user:
        invitation.delete()
        messages.success(request, 'The invitation has been cancelled')
        return True


@authorization_required(auth_functions=(is_submitting_author,))
def move_author(request, project_id):
    """
    Change an author display order. Return the updated authors list html
    if successful. Called via ajax.
    """
    if request.method == 'POST':
        project = Project.objects.get(id=project_id)
        author = Author.objects.get(id=int(request.POST['author_id']))
        direction = request.POST['direction']
        project_authors = project.authors.all()
        n_authors = project_authors.count()
        if author.project == project and n_authors > 1:
            if direction == 'up' and 1 < author.display_order <= n_authors:
                swap_author = project_authors.get(display_order=author.display_order - 1)
            elif direction == 'down' and 1 <= author.display_order < n_authors:
                swap_author = project_authors.get(display_order=author.display_order + 1)
            else:
                raise Http404()
            author.display_order, swap_author.display_order = swap_author.display_order, author.display_order
            author.save()
            swap_author.save()
            authors = project_authors.order_by('display_order')
            return render(request, 'project/author_list.html',
                                  {'project':project, 'authors':authors})
    raise Http404()


@authorization_required(auth_functions=(is_author,))
def project_authors(request, project_id):
    """
    Page displaying author information and actions.
    """
    user = request.user
    project = Project.objects.get(id=project_id)
    authors = project.authors.all().order_by('display_order')
    author = authors.get(user=user)

    AffiliationFormSet = generic_inlineformset_factory(Affiliation,
        fields=('name',), extra=3, max_num=3)

    # Initiate the forms
    affiliation_formset = AffiliationFormSet(instance=author)
    invite_author_form = forms.InviteAuthorForm(project, user)
    add_author_form = forms.AddAuthorForm(project=project)

    if request.method == 'POST':
        if 'edit_affiliations' in request.POST:
            affiliation_formset = AffiliationFormSet(instance=author,
                data=request.POST)
            if edit_affiliations(request, affiliation_formset):
                affiliation_formset = AffiliationFormSet(
                    instance=author)
        elif 'invite_author' in request.POST:
            invite_author_form = forms.InviteAuthorForm(project, user, request.POST)
            if invite_author(request, invite_author_form):
                invite_author_form = forms.InviteAuthorForm(project, user)
        elif 'add_author' in request.POST:
            add_author_form = forms.AddAuthorForm(project=project,
                                                  data=request.POST)
            if add_author(request, add_author_form):
                add_author_form = forms.AddAuthorForm(project=project)
        elif 'remove_author' in request.POST:
            # No form. Just get button value.
            author_id = int(request.POST['remove_author'])
            remove_author(request, author_id)
        elif 'cancel_invitation' in request.POST:
            # No form. Just get button value.
            invitation_id = int(request.POST['cancel_invitation'])
            cancel_invitation(request, invitation_id)

    invitations = project.invitations.filter(invitation_type='author',
        is_active=True)

    return render(request, 'project/project_authors.html', {'project':project,
        'authors':authors, 'invitations':invitations,
        'affiliation_formset':affiliation_formset,
        'invite_author_form':invite_author_form,
        'add_author_form':add_author_form})


@authorization_required(auth_functions=(is_author,))
def edit_references(request, project_id):
    """
    Delete a reference, or reload a formset with 1 form. Return the
    updated reference formset html if successful. Called via ajax.
    """
    project = Project.objects.get(id=project_id)

    if request.method == 'POST':
        if 'add_first' in request.POST:
            ReferenceFormSet = generic_inlineformset_factory(Reference,
                fields=('description',), extra=1, max_num=20, can_delete=False)
            reference_formset = ReferenceFormSet(instance=project)
            return render(request, 'project/reference_list.html', {'reference_formset':reference_formset})
        elif 'remove_reference' in request.POST:
            reference_id = int(request.POST['remove_reference'])
            reference = Reference.objects.get(id=reference_id)
            reference.delete()
            ReferenceFormSet = generic_inlineformset_factory(Reference,
                fields=('description',), extra=0, max_num=20, can_delete=False)
            reference_formset = ReferenceFormSet(instance=project)
            return render(request, 'project/reference_list.html',{'reference_formset':reference_formset})

    return Http404()


@authorization_required(auth_functions=(is_author,))
def project_metadata(request, project_id):
    """
    For editing project metadata
    """
    project = Project.objects.get(id=project_id)

    # There are several forms for different types of metadata
    ReferenceFormSet = generic_inlineformset_factory(Reference,
        fields=('description',), extra=0, max_num=20, can_delete=False)
    TopicFormSet = inlineformset_factory(Project, Topic,
        fields=('description',), extra=0, max_num=20, can_delete=False)
    PublicationFormSet = generic_inlineformset_factory(Publication,
        fields=('citation', 'url'), extra=0, max_num=3, can_delete=False)
    ContactFormSet = generic_inlineformset_factory(Contact,
        fields=('name', 'email', 'affiliation'), extra=0, max_num=3,
        can_delete=False)

    description_form = forms.metadata_forms[project.resource_type](instance=project)
    reference_formset = ReferenceFormSet(instance=project)
    access_form = forms.AccessMetadataForm(instance=project)
    identifier_form = forms.IdentifierMetadataForm(instance=project)
    publication_formset = PublicationFormSet(instance=project)
    contact_formset = ContactFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    # There are several different metadata sections
    if request.method == 'POST':
        # Main description. Process both the description form, and the
        # reference formset
        if 'edit_description' in request.POST:
            description_form = forms.metadata_forms[project.resource_type](request.POST,
                instance=project)
            reference_formset = ReferenceFormSet(request.POST, instance=project)
            if description_form.is_valid() and reference_formset.is_valid():
                description_form.save()
                reference_formset.save()
                messages.success(request, 'Your project metadata has been updated.')
                reference_formset = ReferenceFormSet(instance=project)
            else:
                messages.error(request,
                    'Invalid submission. See errors below.')
        elif 'edit_access' in request.POST:
            access_form = forms.AccessMetadataForm(request.POST, instance=project)
            if access_form.is_valid():
                access_form.save()
                messages.success(request, 'Your access metadata has been updated.')
            else:
                messages.error(request,
                    'Invalid submission. See errors below.')
        elif 'edit_identifiers' in request.POST:
            identifier_form = forms.IdentifierMetadataForm(request.POST,
                                                           instance=project)
            topic_formset = TopicFormSet(request.POST, instance=project)
            if identifier_form.is_valid() and topic_formset.is_valid():
                identifier_form.save()
                topic_formset.save()
                messages.success(request, 'Your identifier metadata has been updated.')
                topic_formset = TopicFormSet(instance=project)
            else:
                messages.error(request,
                    'Invalid submission. See errors below.')

    return render(request, 'project/project_metadata.html', {'project':project,
        'description_form':description_form, 'reference_formset':reference_formset,
        'access_form':access_form, 'identifier_form':identifier_form,
        'publication_formset':publication_formset,
        'contact_formset':contact_formset,
        'topic_formset':topic_formset,
        'messages':messages.get_messages(request)})


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

@authorization_required(auth_functions=(is_author,))
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
            storage_request_form = forms.StorageRequestForm(project=project,
                                                            data=request.POST)
            if storage_request_form.is_valid():
                storage_request_form.instance.project = project
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

    storage_request = StorageRequest.objects.filter(project=project,
                                                    is_active=True).first()

    # Forms
    if storage_request:
        storage_request_form = None
    else:
        storage_request_form = forms.StorageRequestForm(project=project)
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


@authorization_required(auth_functions=(is_author,))
def project_preview(request, project_id):
    """
    Preview what the published project would look like
    """
    user = request.user
    project = Project.objects.get(id=project_id)

    return render(request, 'project/project_preview.html', {'user':user,
        'project':project})


@authorization_required(auth_functions=(is_author,))
def project_submission(request, project_id):
    """
    View submission details regarding a project
    """
    user = request.user
    project = Project.objects.get(id=project_id)

    return render(request, 'project/project_submission.html', {'user':user,
        'project':project})


def process_storage_response(request, storage_response_formset):
    storage_request_id = int(request.POST['storage_response'])

    for storage_response_form in storage_response_formset:
        # Only process the response that was submitted
        if storage_response_form.instance.id == storage_request_id:
            if storage_response_form.is_valid():
                storage_request = storage_response_form.instance
                storage_request.responder = request.user
                storage_request.response_datetime = timezone.now()
                storage_request.is_active = False
                storage_request.save()

                if storage_request.response:
                    project = storage_request.project
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


def published_project(request, published_project_id):
    """
    Displays a published project
    """

    published_project = PublishedProject.objects.get(id=published_project_id)
    authors = published_project.authors.all().order_by('display_order')
    return render(request, 'project/database.html',
                  {'published_project':published_project, 'authors':authors})


@authorization_required(auth_functions=(is_author,))
def edit_metadata_item(request, project_id):
    """
    Either add the first form, or remove an item.

    """

    model_dict = {'reference': Reference, 'publication': Publication,
                  'topic': Topic, 'contact': Contact}
    # Whether the item relation is generic
    is_generic_relation = {'reference': True, 'publication': True,
                        'topic': False, 'contact': True}
    # The fields of each formset
    metadata_item_fields = {'reference': ('description',),
                            'publication': ('citation', 'url'),
                            'topic': ('description',),
                            'contact': ('name', 'affiliation', 'email')}
    max_forms = {'reference': 20, 'publication': 3, 'topic': 20,
                 'contact': 3}

    # These are for the template
    item_labels = {'reference': 'References', 'publication': 'Publications',
                   'topic': 'Topics', 'contact': 'Contacts'}
    form_names = {'reference': 'project-reference-content_type-object_id',
                  'publication': 'project-publication-content_type-object_id',
                  'topic': 'topics',
                  'contact': 'project-contact-content_type-object_id'}

    if request.method == 'POST':
        project = Project.objects.get(id=project_id)
        item = request.POST['item']

        model = model_dict[item]
        # Whether to add the first empty form in the formset
        extra = int('add_first' in request.POST)

        # Use the correct formset factory function
        if is_generic_relation[item]:
            ItemFormSet = generic_inlineformset_factory(model,
                fields=metadata_item_fields[item], extra=extra,
                max_num=max_forms[item], can_delete=False)
        else:
            ItemFormSet = inlineformset_factory(Project, model,
                fields=metadata_item_fields[item], extra=extra,
                max_num=max_forms[item], can_delete=False)

        if 'remove_id' in request.POST:
            # Check this post key
            item_id = int(request.POST['remove_id'])
            model.objects.filter(id=item_id).delete()

        formset = ItemFormSet(instance=project)

        return render(request, 'project/item_list.html',
            {'formset':formset, 'item':item, 'item_label':item_labels[item],
             'form_name':form_names[item], 'max_forms':max_forms[item]})

    else:
        return Http404()
