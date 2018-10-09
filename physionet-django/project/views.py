import os
import pdb
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.forms import formset_factory, inlineformset_factory, modelformset_factory
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.template import loader
from django.urls import reverse
from django.utils import timezone

from . import forms
from .models import (Affiliation, Author, AuthorInvitation, Project,
    PublishedProject, StorageRequest, Reference,
    Topic, Contact, Publication)
from . import utility
import notification.utility as notification
from user.forms import ProfileForm, AssociatedEmailChoiceForm
from user.models import User


def is_admin(user, *args, **kwargs):
    return user.is_admin

def is_author(user, project):
    authors = project.authors.all()
    return (user in [a.user for a in authors])

def is_submitting_author(user, project):
    return user == project.submitting_author

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
            project = Project.objects.get(slug=kwargs['project_slug'])

            for auth_func in auth_functions:
                if auth_func(user, project):
                    return base_function(request, *args, **kwargs)

            raise Http404("Unable to access page")

        return function_wrapper
    return real_decorator


def process_invitation_response(request, invitation_response_formset):
    """
    Process an invitation response.
    Helper function to view: project_home
    """
    user = request.user
    invitation_id = int(request.POST['invitation_response'])
    for invitation_response_form in invitation_response_formset:
        # Only process the response that was submitted
        if invitation_response_form.instance.id == invitation_id:
            invitation_response_form.user = user
            if invitation_response_form.is_valid():
                # Update this invitation, and any other one made to the
                # same user, project, and invitation type
                invitation = invitation_response_form.instance
                project = invitation.project
                invitations = AuthorInvitation.objects.filter(is_active=True,
                    email__in=user.get_emails(), project=project)
                affected_emails = [i.email for i in invitations]
                invitations.update(response=invitation.response,
                    response_datetime=timezone.now(), is_active=False)
                # Create a new Author object
                if invitation.response:
                    author = Author.objects.create(project=project, user=user,
                        display_order=project.authors.count() + 1,
                        corresponding_email=user.get_primary_email())
                    author.import_profile_info()

                notification.invitation_response_notify(invitation,
                                                        affected_emails)
                messages.success(request,'The invitation has been {0}.'.format(
                    notification.RESPONSE_ACTIONS[invitation.response]))


@login_required
def project_home(request):
    """
    Project home page, listing:
    - authoring projects
    - project invitations and response form
    """
    user = request.user
    projects = Project.objects.filter(authors__in=user.authorships.all())

    InvitationResponseFormSet = modelformset_factory(AuthorInvitation,
        form=forms.InvitationResponseForm, extra=0)

    if request.method == 'POST':
        invitation_response_formset = InvitationResponseFormSet(request.POST)
        process_invitation_response(request, invitation_response_formset)

    invitation_response_formset = InvitationResponseFormSet(
        queryset=AuthorInvitation.get_user_invitations(user))

    return render(request, 'project/project_home.html', {'projects':projects,
        'invitation_response_formset':invitation_response_formset})


@login_required
def create_project(request):
    user = request.user

    if request.method == 'POST':
        form = forms.CreateProjectForm(user=user, data=request.POST)
        if form.is_valid():
            project = form.save()
            return redirect('project_overview', project_slug=project.slug)
    else:
        form = forms.CreateProjectForm(user=user)

    return render(request, 'project/create_project.html', {'form':form})


def project_overview_redirect(request, project_slug):
    return redirect(reverse('project_overview', args=[project_slug]))


@authorization_required(auth_functions=(is_author, is_admin))
def project_overview(request, project_slug):
    """
    Overview page of a project
    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    admin_inspect = user.is_admin and not is_author(user, project)

    published_projects = project.published_projects.all().order_by('publish_datetime') if project.published else None

    return render(request, 'project/project_overview.html',
                  {'project':project, 'admin_inspect':admin_inspect,
                   'published_projects':published_projects})


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



def remove_author(request, author_id):
    """
    Remove an author from a project
    Helper function for `project_authors`.
    """
    user = request.user
    author = Author.objects.get(id=author_id)
    project = author.project

    if project.submitting_author == user:
        authors = project.authors.all()
        # Reset the corresponding author if necessary
        if author.is_corresponding:
            submitting_author = authors.get(user=project.submitting_author)
            submitting_author.is_corresponding = True
            submitting_author.save()
        # Other author orders may have to be decreased when this author
        # is removed
        higher_authors = authors.filter(display_order__gt=author.display_order)
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
    invitation = AuthorInvitation.objects.get(id=invitation_id)
    if invitation.project.submitting_author == user:
        invitation.delete()
        messages.success(request, 'The invitation has been cancelled')
        return True


@authorization_required(auth_functions=(is_submitting_author,))
def move_author(request, project_slug):
    """
    Change an author display order. Return the updated authors list html
    if successful. Called via ajax.
    """
    if request.method == 'POST':
        project = Project.objects.get(slug=project_slug)
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
def edit_affiliation(request, project_slug):
    """
    Function accessed via ajax for editing an author's affiliation in a
    formset.

    Either add the first form, or remove an affiliation, returning the
    rendered template of the formset.

    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    author = project.authors.get(user=user)

    # Reload the formset with the first empty form
    if request.method == 'GET' and 'add_first' in request.GET:
        extra_forms = 1
    # Remove an object
    elif request.method == 'POST' and 'remove_id' in request.POST:
        extra_forms = 0
        item_id = int(request.POST['remove_id'])
        # Make sure that the affiliation belongs to the user
        affiliation = Affiliation.objects.get(id=item_id)
        if author == affiliation.author:
            affiliation.delete()
        else:
            raise Http404()

    AffiliationFormSet = inlineformset_factory(parent_model=Author,
        model=Affiliation, fields=('name',), extra=extra_forms,
        max_num=forms.AffiliationFormSet.max_forms, can_delete=False,
        formset=forms.AffiliationFormSet, validate_max=True)
    formset = AffiliationFormSet(instance=author)
    edit_url = reverse('edit_affiliation', args=[project.slug])

    return render(request, 'project/item_list.html',
            {'formset':formset, 'item':'affiliation', 'item_label':formset.item_label,
             'form_name':formset.form_name, 'add_item_url':edit_url,
             'remove_item_url':edit_url})


@authorization_required(auth_functions=(is_author, is_admin))
def project_authors(request, project_slug):
    """
    Page displaying author information and actions.
    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    authors = project.authors.all().order_by('display_order')
    admin_inspect = user.is_admin and user not in [a.user for a in authors]

    if admin_inspect:
        (affiliation_formset, invite_author_form, corresponding_author_form,
         corresponding_email_form) = None, None, None, None
    else:
        author = authors.get(user=user)
        AffiliationFormSet = inlineformset_factory(parent_model=Author,
            model=Affiliation, fields=('name',), extra=0,
            max_num=forms.AffiliationFormSet.max_forms, can_delete=False,
            formset = forms.AffiliationFormSet, validate_max=True)
        affiliation_formset = AffiliationFormSet(instance=author)

        if user == project.submitting_author:
            invite_author_form = forms.InviteAuthorForm(project=project,
                inviter=user)
            corresponding_author_form = forms.CorrespondingAuthorForm(
                project=project)
        else:
            invite_author_form, corresponding_author_form = None, None

        if user == project.corresponding_author().user:
            corresponding_email_form = AssociatedEmailChoiceForm(
                user=user, selection_type='corresponding', author=author)
        else:
            corresponding_email_form = None

    if request.method == 'POST':
        if 'edit_affiliations' in request.POST:
            affiliation_formset = AffiliationFormSet(instance=author,
                data=request.POST)
            if edit_affiliations(request, affiliation_formset):
                affiliation_formset = AffiliationFormSet(
                    instance=author)
        elif 'invite_author' in request.POST:
            invite_author_form = forms.InviteAuthorForm(project=project,
                inviter=user, data=request.POST)
            if invite_author_form.is_valid():
                invite_author_form.save()
                target_email = invite_author_form.cleaned_data['email']
                notification.invitation_notify(request, invite_author_form,
                                               target_email)
                messages.success(request,
                    'An invitation has been sent to: {0}'.format(target_email))
                invite_author_form = forms.InviteAuthorForm(project, user)
            else:
                messages.error(request, 'Submission unsuccessful. See form for errors.')
        elif 'remove_author' in request.POST:
            # No form. Just get button value.
            author_id = int(request.POST['remove_author'])
            remove_author(request, author_id)
        elif 'cancel_invitation' in request.POST:
            # No form. Just get button value.
            invitation_id = int(request.POST['cancel_invitation'])
            cancel_invitation(request, invitation_id)
        elif 'corresponding_author' in request.POST:
            corresponding_author_form = forms.CorrespondingAuthorForm(
                project=project, data=request.POST)
            if user == project.submitting_author and corresponding_author_form.is_valid():
                corresponding_author_form.update_corresponder()
                messages.success(request, 'The corresponding author has been updated.')
        elif 'corresponding_email' in request.POST:
            corresponding_email_form = AssociatedEmailChoiceForm(
                user=user, selection_type='corresponding', author=author,
                data=request.POST)
            if corresponding_email_form.is_valid():
                author.corresponding_email = corresponding_email_form.cleaned_data['associated_email']
                author.save()
                messages.success(request, 'Your corresponding email has been updated.')

    invitations = project.authorinvitations.filter(is_active=True)
    edit_affiliations_url = reverse('edit_affiliation', args=[project.slug])
    return render(request, 'project/project_authors.html', {'project':project,
        'authors':authors, 'invitations':invitations,
        'affiliation_formset':affiliation_formset,
        'invite_author_form':invite_author_form, 'admin_inspect':admin_inspect,
        'corresponding_author_form':corresponding_author_form,
        'corresponding_email_form':corresponding_email_form,
        'add_item_url':edit_affiliations_url, 'remove_item_url':edit_affiliations_url})


@authorization_required(auth_functions=(is_author,))
def edit_metadata_item(request, project_slug):
    """
    Function accessed via ajax for editing a project's related item
    in a formset.

    Either add the first form, or remove an item, returning the rendered
    template of the formset.

    """
    model_dict = {'reference': Reference, 'publication': Publication,
                  'topic': Topic}
    # Whether the item relation is generic
    is_generic_relation = {'reference': True, 'publication':True,
                           'topic': False}

    custom_formsets = {'reference':forms.ReferenceFormSet,
                       'publication':forms.PublicationFormSet,
                       'topic':forms.TopicFormSet}

    # The fields of each formset
    metadata_item_fields = {'reference': ('description',),
                            'publication': ('citation', 'url'),
                            'topic': ('description',)}

    project = Project.objects.get(slug=project_slug)

    # Reload the formset with the first empty form
    if request.method == 'GET' and 'add_first' in request.GET:
        item = request.GET['item']
        model = model_dict[item]
        extra_forms = 1
    # Remove an object
    elif request.method == 'POST' and 'remove_id' in request.POST:
        item = request.POST['item']
        model = model_dict[item]
        extra_forms = 0
        item_id = int(request.POST['remove_id'])
        model.objects.filter(id=item_id).delete()

    # Create the formset
    if is_generic_relation[item]:
        ItemFormSet = generic_inlineformset_factory(model,
            fields=metadata_item_fields[item], extra=extra_forms,
            max_num=custom_formsets[item].max_forms, can_delete=False,
            formset=custom_formsets[item], validate_max=True)
    else:
        ItemFormSet = inlineformset_factory(parent_model=Project, model=model,
            fields=metadata_item_fields[item], extra=extra_forms,
            max_num=custom_formsets[item].max_forms, can_delete=False,
            formset=custom_formsets[item], validate_max=True)

    formset = ItemFormSet(instance=project)
    edit_url = reverse('edit_metadata_item', args=[project.slug])

    return render(request, 'project/item_list.html',
            {'formset':formset, 'item':item, 'item_label':formset.item_label,
             'form_name':formset.form_name, 'add_item_url':edit_url,
             'remove_item_url':edit_url})

@authorization_required(auth_functions=(is_author, is_admin))
def project_metadata(request, project_slug):
    """
    For editing project metadata
    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    admin_inspect = user.is_admin and not is_author(user, project)

    # There are several forms for different types of metadata
    ReferenceFormSet = generic_inlineformset_factory(Reference,
        fields=('description',), extra=0,
        max_num=forms.ReferenceFormSet.max_forms, can_delete=False,
        formset=forms.ReferenceFormSet)

    description_form = forms.METADATA_FORMS[project.resource_type](instance=project)
    reference_formset = ReferenceFormSet(instance=project)

    if request.method == 'POST':
        description_form = forms.METADATA_FORMS[project.resource_type](data=request.POST,
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
    edit_url = reverse('edit_metadata_item', args=[project.slug])

    return render(request, 'project/project_metadata.html', {'project':project,
        'description_form':description_form, 'reference_formset':reference_formset,
        'messages':messages.get_messages(request), 'admin_inspect':admin_inspect,
        'add_item_url':edit_url, 'remove_item_url':edit_url})


@authorization_required(auth_functions=(is_author, is_admin))
def project_access(request, project_slug):
    """
    Page to edit project access policy

    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    admin_inspect = user.is_admin and not is_author(user, project)

    access_form = forms.AccessMetadataForm(instance=project)

    if request.method == 'POST':
        access_form = forms.AccessMetadataForm(request.POST, instance=project)
        if access_form.is_valid():
            access_form.save()
            messages.success(request, 'Your access metadata has been updated.')
        else:
            messages.error(request,
                'Invalid submission. See errors below.')

    return render(request, 'project/project_access.html', {'project':project,
                  'access_form':access_form, 'admin_inspect':admin_inspect})


@authorization_required(auth_functions=(is_author, is_admin))
def project_identifiers(request, project_slug):
    """
    Page to edit external project identifiers

    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    admin_inspect = user.is_admin and not is_author(user, project)

    TopicFormSet = inlineformset_factory(Project, Topic,
        fields=('description',), extra=0, max_num=forms.TopicFormSet.max_forms,
        can_delete=False, formset=forms.TopicFormSet, validate_max=True)
    PublicationFormSet = generic_inlineformset_factory(Publication,
        fields=('citation', 'url'), extra=0,
        max_num=forms.PublicationFormSet.max_forms, can_delete=False,
        formset=forms.PublicationFormSet, validate_max=True)

    publication_formset = PublicationFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    if request.method == 'POST':
        publication_formset = PublicationFormSet(request.POST,
                                                 instance=project)
        topic_formset = TopicFormSet(request.POST, instance=project)
        if publication_formset.is_valid() and topic_formset.is_valid():
            print([f.instance.id for f in topic_formset.forms])
            publication_formset.save()
            topic_formset.save()
            messages.success(request, 'Your identifier information has been updated.')
            topic_formset = TopicFormSet(instance=project)
            publication_formset = PublicationFormSet(instance=project)
        else:
            messages.error(request, 'Invalid submission. See errors below.')

    edit_url = reverse('edit_metadata_item', args=[project.slug])
    return render(request, 'project/project_identifiers.html',
        {'project':project, 'publication_formset':publication_formset,
         'topic_formset':topic_formset, 'add_item_url':edit_url,
         'remove_item_url':edit_url})


@authorization_required(auth_functions=(is_author, is_admin))
def project_files_panel(request, project_slug):
    """
    Return the file panel for the project, along with the forms used to
    manipulate them. Called via ajax to navigate directories.
    """
    project = Project.objects.get(slug=project_slug)
    subdir = request.GET['subdir']

    display_files, display_dirs = project.get_directory_content(
        subdir=subdir)

    # Breadcrumbs
    dir_breadcrumbs = utility.get_dir_breadcrumbs(subdir)
    parent_dir = os.path.split(subdir)[0]

    # Forms
    upload_files_form = forms.UploadFilesForm(project=project)
    create_folder_form = forms.CreateFolderForm(project=project)
    rename_item_form = forms.RenameItemForm(project=project)
    move_items_form = forms.MoveItemsForm(project=project, subdir=subdir)
    delete_items_form = forms.EditItemsForm(project=project)

    return render(request, 'project/project_files_panel.html',
        {'project':project, 'subdir':subdir,
         'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
         'display_files':display_files, 'display_dirs':display_dirs,
         'upload_files_form':upload_files_form,
         'create_folder_form':create_folder_form,
         'rename_item_form':rename_item_form,
         'move_items_form':move_items_form,
         'delete_items_form':delete_items_form,})

def process_items(request, form):
    """
    Process the file manipulation items with the appropriate form and
    action. Returns the working subdirectory.
    """
    if form.is_valid():
        messages.success(request, form.perform_action())
        return form.cleaned_data['subdir']
    else:
        messages.error(request, utility.get_form_errors(form))
        # If there are no errors with the subdir, keep the same subdir.
        if 'subdir' in form.cleaned_data:
            return form.cleaned_data['subdir']
        else:
            return ''

@authorization_required(auth_functions=(is_author, is_admin))
def project_files(request, project_slug):
    "View and manipulate files in a project"
    project = Project.objects.get(slug=project_slug)
    admin_inspect = request.user.is_admin and not is_author(request.user, project)
    storage_info = utility.get_storage_info(project.storage_allowance*1024**2,
            project.storage_used())

    if request.method == 'POST':
        if request.user != project.submitting_author:
            return Http404()

        if 'request_storage' in request.POST:
            storage_request_form = forms.StorageRequestForm(project=project,
                                                            data=request.POST)
            if storage_request_form.is_valid():
                storage_request_form.instance.project = project
                storage_request_form.save()
                messages.success(request, 'Your storage request has been received.')
            else:
                messages.error(request, utility.get_form_errors(storage_request_form))
            subdir = ''
        elif 'upload_files' in request.POST:
            form = forms.UploadFilesForm(project=project, data=request.POST, files=request.FILES)
            subdir = process_items(request, form)
        elif 'create_folder' in request.POST:
            form = forms.CreateFolderForm(project=project, data=request.POST)
            subdir = process_items(request, form)
        elif 'rename_item' in request.POST:
            form = forms.RenameItemForm(project=project, data=request.POST)
            subdir = process_items(request, form)
        elif 'move_items' in request.POST:
            form = forms.MoveItemsForm(project=project, data=request.POST)
            subdir = process_items(request, form)
        elif 'delete_items' in request.POST:
            form = forms.EditItemsForm(project=project, data=request.POST)
            subdir = process_items(request, form)
        else:
            subdir = ''

        # Reload the storage info.
        storage_info = utility.get_storage_info(project.storage_allowance*1024**2,
            project.storage_used())
    else:
        # The subdirectory is just the base. Ajax calls to the file
        # panel will not call this view.
        subdir = ''

    storage_request = StorageRequest.objects.filter(project=project,
                                                    is_active=True).first()
    # Forms
    if storage_request:
        storage_request_form = None
    else:
        storage_request_form = forms.StorageRequestForm(project=project)

    upload_files_form = forms.UploadFilesForm(project=project)
    create_folder_form = forms.CreateFolderForm(project=project)
    rename_item_form = forms.RenameItemForm(project=project)
    move_items_form = forms.MoveItemsForm(project=project, subdir=subdir)
    delete_items_form = forms.EditItemsForm(project=project)

    # The contents of the directory
    display_files, display_dirs = project.get_directory_content(subdir=subdir)
    dir_breadcrumbs = utility.get_dir_breadcrumbs(subdir)

    return render(request, 'project/project_files.html', {'project':project,
        'subdir':subdir,
        'display_files':display_files,
        'display_dirs':display_dirs,
        'storage_info':storage_info,
        'storage_request':storage_request,
        'storage_request_form':storage_request_form,
        'upload_files_form':upload_files_form,
        'create_folder_form':create_folder_form,
        'rename_item_form':rename_item_form,
        'move_items_form':move_items_form,
        'delete_items_form':delete_items_form, 'admin_inspect':admin_inspect,
        'dir_breadcrumbs':dir_breadcrumbs})


@authorization_required(auth_functions=(is_author, is_admin))
def serve_project_file(request, project_slug, file_name):
    """
    Serve a file in a project. file_name is file path relative to
    project file root.
    """
    project = Project.objects.get(slug=project_slug)
    file_path = os.path.join(project.file_root(), file_name)
    return utility.serve_file(request, file_path)

@authorization_required(auth_functions=(is_author, is_admin))
def preview_files_panel(request, project_slug):
    """
    Return the file panel for the project, along with the forms used to
    manipulate them. Called via ajax to navigate directories.
    """
    project = Project.objects.get(slug=project_slug)
    subdir = request.GET['subdir']

    display_files, display_dirs = project.get_directory_content(
        subdir=subdir)

    # Breadcrumbs
    dir_breadcrumbs = utility.get_dir_breadcrumbs(subdir)
    parent_dir = os.path.split(subdir)[0]

    return render(request, 'project/preview_files_panel.html',
        {'project':project, 'subdir':subdir,
         'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
         'display_files':display_files, 'display_dirs':display_dirs})


@authorization_required(auth_functions=(is_author, is_admin))
def project_proofread(request, project_slug):
    """
    Proofreading page for project before submission
    """
    project = Project.objects.get(slug=project_slug)
    admin_inspect = request.user.is_admin and not is_author(request.user, project)

    return render(request, 'project/project_proofread.html', {'project':project,
        'admin_inspect':admin_inspect})

@authorization_required(auth_functions=(is_author, is_admin))
def project_preview(request, project_slug):
    """
    Preview what the published project would look like. Includes
    serving files.

    """
    project = Project.objects.get(slug=project_slug)
    admin_inspect = request.user.is_admin and not is_author(request.user, project)

    authors = project.authors.all().order_by('display_order')
    author_info = [utility.AuthorInfo(a) for a in authors]
    invitations = project.authorinvitations.filter(is_active=True)
    corresponding_author = authors.get(is_corresponding=True)

    references = project.references.all()
    publications = project.publications.all()
    topics = project.topics.all()

    is_submittable = project.is_submittable()
    version_clash = False

    if is_submittable:
        messages.success(request, 'The project has passed all automatic checks.')
    else:
        for e in project.submit_errors:
            messages.error(request, e)
            if 'version' in e:
                version_clash = True

    display_files, display_dirs = project.get_directory_content()
    dir_breadcrumbs = utility.get_dir_breadcrumbs('')

    return render(request, 'project/project_preview.html', {
        'project':project, 'display_files':display_files, 'display_dirs':display_dirs,
        'author_info':author_info, 'corresponding_author':corresponding_author,
        'invitations':invitations, 'references':references,
        'publications':publications, 'topics':topics,
        'is_submittable':is_submittable, 'version_clash':version_clash,
        'admin_inspect':admin_inspect, 'dir_breadcrumbs':dir_breadcrumbs})


@authorization_required(auth_functions=(is_author,))
def check_submittable(request, project_slug):
    """
    Check whether a project is submittable
    """
    project = Project.objects.get(slug=project_slug)

    result = project.is_submittable()

    return JsonResponse({'is_submittable':result,
        'submit_errors':project.submit_errors})


@authorization_required(auth_functions=(is_author, is_admin))
def project_submission(request, project_slug):
    """
    View submission details regarding a project, submit the project
    for review, cancel a submission, approve a submission, and withdraw
    approval.
    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    authors = project.authors.all().order_by('display_order')
    all_submissions = project.submissions.all().order_by('submission_datetime')
    admin_inspect = user.is_admin and user not in [a.user for a in authors]
    context = {'project':project, 'admin_inspect':admin_inspect,
               'all_submissions':all_submissions}

    if request.method == 'POST':
        if project.under_submission:
            submission = project.submissions.get(is_active=True)
        # Project is submitted for review
        if 'submit_project' in request.POST and not project.under_submission and user == project.submitting_author:
            if project.is_submittable():
                project.submit()
                notification.submit_notify(project)
                messages.success(request, 'Your project has been submitted. You will be notified when an editor is assigned.')
            else:
                messages.error(request, 'Fix the errors before submitting')
        # Author approves publication
        elif 'approve_publish' in request.POST:
            author = authors.get(user=user)
            if submission.status == 3 and not author.approved_publish:
                author.approved_publish = True
                author.save()
                messages.success(request, 'You have approved the publication.')
            else:
                raise Http404()

    if project.under_submission:
        submission = project.submissions.get(is_active=True)
        context['submission'] = submission
        context['authors'] = authors
        if not admin_inspect:
            context['author'] = authors.get(user=user)

    return render(request, 'project/project_submission.html', context)


@authorization_required(auth_functions=(is_author, is_admin))
def project_submission_details(request, project_slug, submission_number):
    """
    Full details for a submission
    """
    user = request.user
    project = Project.objects.get(slug=project_slug)
    admin_inspect = user.is_admin and not is_author(user, project)
    submission = project.submissions.get(number=submission_number)
    return render(request, 'project/project_submission_details.html',
        {'project':project, 'admin_inspect':admin_inspect,
         'submission':submission})


def published_files_panel(request, published_project_slug):
    """
    Return the file panel for the published project, for all access
    policies
    """
    published_project = PublishedProject.objects.get(slug=published_project_slug)
    subdir = request.GET['subdir']

    display_files, display_dirs = published_project.get_directory_content(
        subdir=subdir)
    total_size = utility.readable_size(published_project.storage_size)

    # Breadcrumbs
    dir_breadcrumbs = utility.get_dir_breadcrumbs(subdir)
    parent_dir = os.path.split(subdir)[0]

    if published_project.access_policy:
        template = 'project/protected_files_panel.html'
    else:
        template = 'project/open_files_panel.html'

    return render(request, template,
        {'published_project':published_project, 'subdir':subdir,
         'dir_breadcrumbs':dir_breadcrumbs, 'total_size':total_size,
         'parent_dir':parent_dir,
         'display_files':display_files, 'display_dirs':display_dirs})


def serve_published_project_file(request, published_project_slug, file_name):
    """
    Serve a protected file of a published project

    """
    # todo: protect this view
    published_project = PublishedProject.objects.get(slug=published_project_slug)
    file_path = os.path.join(published_project.file_root(), file_name)
    return utility.serve_file(request, file_path)


def database(request, published_project):
    """
    Displays a published database project
    """
    authors = published_project.authors.all().order_by('display_order')
    author_info = [utility.AuthorInfo(a) for a in authors]
    references = published_project.references.all()
    publications = published_project.publications.all()
    topics = published_project.topics.all()
    contact = Contact.objects.get(published_project=published_project)

    # The file and directory contents
    display_files, display_dirs = published_project.get_directory_content()

    dir_breadcrumbs = utility.get_dir_breadcrumbs('')
    total_size = utility.readable_size(published_project.storage_size)

    return render(request, 'project/database.html',
        {'published_project':published_project, 'author_info':author_info,
         'references':references, 'publications':publications, 'topics':topics,
         'contact':contact, 'dir_breadcrumbs':dir_breadcrumbs,
         'total_size':total_size, 'display_files':display_files,
         'display_dirs':display_dirs})


def published_project(request, published_project_slug):
    """
    Displays a published project
    """

    published_project = PublishedProject.objects.get(slug=published_project_slug)

    if published_project.resource_type == 0:
        return database(request, published_project)
