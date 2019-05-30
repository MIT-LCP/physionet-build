import os
import pdb
import re
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import (ObjectDoesNotExist, PermissionDenied,
    ValidationError)
from django.db import transaction
from django.forms import (formset_factory, inlineformset_factory,
    modelformset_factory)
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from project import forms
from project.models import (Affiliation, Author, AuthorInvitation,
    ActiveProject, PublishedProject, StorageRequest, Reference,
    ArchivedProject, ProgrammingLanguage, Topic, Contact, Publication,
    PublishedAuthor, EditLog, CopyeditLog, DUASignature, CoreProject, GCP)
from project import utility
from project.validators import validate_filename
import notification.utility as notification
from physionet.utility import serve_file
from user.forms import ProfileForm, AssociatedEmailChoiceForm
from user.models import User
from console.utility import add_email_bucket_access

from dal import autocomplete


def project_auth(auth_mode=0, post_auth_mode=0):
    """
    Authorization decorator for project. Also adds project information
    to kwargs.

    auth_mode is one of the following:
    - 0 : the user must be an author.
    - 1 : the user must be the submitting author.
    - 2 : the user must be an author or an admin

    post_auth_mode is one of the following and applies only to post:
    - 0 : no additional check
    - 1 : the user must be an author, and the project must be in one of
          its author editable stages.
    - 2 : the user must be the submitting author, and the project must
          be in one of its author editable stages.
    """
    def real_decorator(base_view):
        @login_required
        def view_wrapper(request, *args, **kwargs):
            user = request.user
            try:
                project = ActiveProject.objects.get(
                    slug=kwargs['project_slug'])
            except ObjectDoesNotExist:
                raise PermissionDenied()
            authors = project.authors.all().order_by('display_order')

            is_author = bool(authors.filter(user=user))
            is_submitting = (user == authors.get(is_submitting=True).user)

            if auth_mode == 0:
                allow = is_author
            elif auth_mode == 1:
                allow = is_submitting
            elif auth_mode == 2:
                allow = is_author or user.is_admin

            if request.method == 'POST':
                if post_auth_mode == 1:
                    allow = is_author and project.author_editable()
                elif post_auth_mode == 2:
                    allow = is_submitting and project.author_editable()

            if allow:
                kwargs['user'] = user
                kwargs['project'] = project
                kwargs['authors'] = authors
                kwargs['is_author'] = is_author
                kwargs['is_submitting'] = is_submitting
                return base_view(request, *args, **kwargs)
            raise PermissionDenied()
        return view_wrapper
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
                author_imported = False
                if invitation.response:
                    author = Author.objects.create(project=project, user=user,
                        display_order=project.authors.count() + 1,
                        corresponding_email=user.get_primary_email())
                    author_imported = author.import_profile_info()

                notification.invitation_response_notify(invitation,
                                                        affected_emails)
                messages.success(request,'The invitation has been {0}.'.format(
                    notification.RESPONSE_ACTIONS[invitation.response]))
                if not author_imported and invitation.response:
                    return True, project
                elif invitation.response:
                    return False, project
                return False, False



@login_required
def project_home(request):
    """
    Project home page, listing:
    - active projects
    - published projects
    - project invitations and response form
    """
    user = request.user

    InvitationResponseFormSet = modelformset_factory(AuthorInvitation,
        form=forms.InvitationResponseForm, extra=0)

    if request.method == 'POST':
        invitation_response_formset = InvitationResponseFormSet(request.POST,
            queryset=AuthorInvitation.get_user_invitations(user))
        imported, project = process_invitation_response(request, invitation_response_formset)
        if project:
            if imported:
                messages.info(request,'Please fill in the affiliation at the end of the page.')
            return redirect('project_authors', project_slug=project.slug)

    active_authors = Author.objects.filter(user=user,
        content_type=ContentType.objects.get_for_model(ActiveProject))
    archived_authors = Author.objects.filter(user=user,
        content_type=ContentType.objects.get_for_model(ArchivedProject))
    published_authors = PublishedAuthor.objects.filter(user=user,
        project__is_latest_version=True)

    # Get the various projects.
    projects = [a.project for a in active_authors]
    published_projects = [a.project for a in published_authors]
    for p in published_projects:
        p.new_button = p.can_publish_new(user)

    pending_author_approvals = []
    missing_affiliations = []
    for p in projects:
        if (p.submission_status == 50
                and not p.authors.get(user=user).approval_datetime):
            pending_author_approvals.append(p)
        if (p.submission_status == 0
                and p.authors.get(user=user).affiliations.count() == 0):
            missing_affiliations.append(
                [p, p.authors.get(user=user).creation_date])
    rejected_projects = [a.project for a in archived_authors if a.project.archive_reason == 3]

    invitation_response_formset = InvitationResponseFormSet(
        queryset=AuthorInvitation.get_user_invitations(user))

    return render(request, 'project/project_home.html', {
        'projects': projects, 'published_projects': published_projects,
        'rejected_projects': rejected_projects,
        'missing_affiliations': missing_affiliations,
        'pending_author_approvals': pending_author_approvals,
        'invitation_response_formset': invitation_response_formset})

@login_required
def create_project(request):
    user = request.user

    n_submitting = Author.objects.filter(user=user, is_submitting=True,
        content_type=ContentType.objects.get_for_model(ActiveProject)).count()
    if n_submitting >= ActiveProject.MAX_SUBMITTING_PROJECTS:
        return render(request, 'project/project_limit_reached.html',
            {'max_projects':ActiveProject.MAX_SUBMITTING_PROJECTS})

    if request.method == 'POST':
        form = forms.CreateProjectForm(user=user, data=request.POST)
        if form.is_valid():
            project = form.save()
            return redirect('project_overview', project_slug=project.slug)
    else:
        form = forms.CreateProjectForm(user=user)

    return render(request, 'project/create_project.html', {'form':form})

@login_required
def new_project_version(request, project_slug):
    """
    Publish a new version of a project

    """
    user = request.user

    n_submitting = Author.objects.filter(user=user, is_submitting=True,
        content_type=ContentType.objects.get_for_model(ActiveProject)).count()
    if n_submitting >= ActiveProject.MAX_SUBMITTING_PROJECTS:
        return render(request, 'project/project_limit_reached.html',
            {'max_projects':ActiveProject.MAX_SUBMITTING_PROJECTS})

    previous_projects = PublishedProject.objects.filter(
        slug=project_slug).order_by('-version_order')
    latest_project = previous_projects.first()

    # Only submitting author can make new. Also can only have one new version
    # of this project out at a time.
    if not latest_project.can_publish_new(user):
        return redirect('project_home')

    if request.method == 'POST':
        form = forms.NewProjectVersionForm(user=user,
            latest_project=latest_project, previous_projects=previous_projects,
            data=request.POST)
        if form.is_valid():
            project = form.save()
            return redirect('project_overview', project_slug=project.slug)
    else:
        form = forms.NewProjectVersionForm(user=user,
            latest_project=latest_project, previous_projects=previous_projects)

    return render(request, 'project/new_project_version.html', {'form':form,
        'project':latest_project, 'previous_projects':previous_projects})


def project_overview_redirect(request, project_slug):
    return redirect('project_overview', project_slug=project_slug)


@project_auth(auth_mode=0)
def project_overview(request, project_slug, **kwargs):
    """
    Overview page of a project
    """
    project, is_submitting = kwargs['project'], kwargs['is_submitting']
    under_submission = project.under_submission()

    if request.method == 'POST' and 'delete_project' in request.POST and is_submitting and not under_submission:
        project.fake_delete()
        return redirect('delete_project_success')

    return render(request, 'project/project_overview.html',
        {'project':project, 'is_submitting':is_submitting,
         'under_submission':under_submission,
         'submitting_author':kwargs['authors'].get(is_submitting=True)})


@login_required
def delete_project_success(request):
    return render(request, 'project/delete_project_success.html')


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


def remove_author(request, author_id, project, authors):
    """
    Remove an author from a project
    Helper function for `project_authors`.
    """
    rm_author = Author.objects.filter(id=author_id)
    if rm_author:
        rm_author = rm_author.get()
    else:
        raise Http404()

    if rm_author in authors:
        # Reset the corresponding author if necessary
        if rm_author.is_corresponding:
            submitting_author = authors.get(is_submitting=True)
            submitting_author.is_corresponding = True
            submitting_author.save()
        # Other author orders may have to be decreased when this author
        # is removed
        higher_authors = authors.filter(display_order__gt=rm_author.display_order)
        rm_author.delete()
        if higher_authors:
            for author in higher_authors:
                author.display_order -= 1
                author.save()

        messages.success(request, 'The author has been removed from the project')

def cancel_invitation(request, invitation_id, project):
    """
    Cancel an author invitation for a project.
    Helper function for `project_authors`.
    """
    invitation = AuthorInvitation.objects.filter(id=invitation_id)
    if invitation:
        invitation = invitation.get()
    else:
        raise Http404()
    if invitation.project == project:
        invitation.delete()
        messages.success(request, 'The invitation has been cancelled')


@project_auth(auth_mode=1, post_auth_mode=2)
def move_author(request, project_slug, **kwargs):
    """
    Change an author display order. Return the updated authors list html
    if successful. Called via ajax.
    """
    project, authors, is_submitting = (kwargs[k] for k in
        ('project', 'authors', 'is_submitting'))

    if request.method == 'POST':
        author = authors.get(id=int(request.POST['author_id']))
        direction = request.POST['direction']
        n_authors = authors.count()
        if n_authors > 1:
            if direction == 'up' and 1 < author.display_order <= n_authors:
                swap_author = authors.get(display_order=author.display_order - 1)
            elif direction == 'down' and 1 <= author.display_order < n_authors:
                swap_author = authors.get(display_order=author.display_order + 1)
            else:
                raise Http404()
            with transaction.atomic():
                orig_order = author.display_order
                swap_order = swap_author.display_order
                author.display_order = 0
                author.save(update_fields=('display_order',))
                swap_author.display_order = orig_order
                swap_author.save(update_fields=('display_order',))
                author.display_order = swap_order
                author.save(update_fields=('display_order',))
            authors = project.get_author_info()
            return render(request, 'project/author_list.html',
                {'project':project, 'authors':authors,
                'is_submitting':is_submitting})
    raise Http404()


@project_auth(auth_mode=0, post_auth_mode=1)
def edit_affiliation(request, project_slug, **kwargs):
    """
    Function accessed via ajax for editing an author's affiliation in a
    formset.

    Either add the first form, or remove an affiliation, returning the
    rendered template of the formset.

    """
    project, authors = kwargs['project'], kwargs['authors']
    author = authors.get(user=request.user)

    if project.submission_status not in [0, 30]:
        raise Http404()

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


@project_auth(auth_mode=0, post_auth_mode=1)
def project_authors(request, project_slug, **kwargs):
    """
    Page displaying author information and actions.
    """
    user, project, authors, is_submitting, = (kwargs[k] for k in
        ('user', 'project', 'authors', 'is_submitting'))

    author = authors.get(user=user)
    AffiliationFormSet = inlineformset_factory(parent_model=Author,
        model=Affiliation, fields=('name',), extra=0,
        max_num=forms.AffiliationFormSet.max_forms, can_delete=False,
        formset = forms.AffiliationFormSet, validate_max=True)
    affiliation_formset = AffiliationFormSet(instance=author)

    if is_submitting:
        invite_author_form = forms.InviteAuthorForm(project=project,
            inviter=user)
        corresponding_author_form = forms.CorrespondingAuthorForm(
            project=project)
    else:
        invite_author_form, corresponding_author_form = None, None

    if author.is_corresponding:
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
        elif 'invite_author' in request.POST and is_submitting:
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
        elif 'remove_author' in request.POST and is_submitting:
            # No form. Just get button value.
            author_id = int(request.POST['remove_author'])
            remove_author(request, author_id, project, authors)
        elif 'cancel_invitation' in request.POST and is_submitting:
            # No form. Just get button value.
            invitation_id = int(request.POST['cancel_invitation'])
            cancel_invitation(request, invitation_id, project)
        elif 'corresponding_author' in request.POST and is_submitting:
            corresponding_author_form = forms.CorrespondingAuthorForm(
                project=project, data=request.POST)
            if corresponding_author_form.is_valid():
                corresponding_author_form.update_corresponder()
                messages.success(request, 'The corresponding author has been updated.')
            else:
                messages.error(request, 'Submission unsuccessful. See form for errors.')
        elif 'corresponding_email' in request.POST and author.is_corresponding:
            corresponding_email_form = AssociatedEmailChoiceForm(
                user=user, selection_type='corresponding', author=author,
                data=request.POST)
            if corresponding_email_form.is_valid():
                author.corresponding_email = corresponding_email_form.cleaned_data['associated_email']
                author.save()
                messages.success(request, 'Your corresponding email has been updated.')
            else:
                messages.error(request, 'Submission unsuccessful. See form for errors.')

    authors = project.get_author_info()
    invitations = project.authorinvitations.filter(is_active=True)
    edit_affiliations_url = reverse('edit_affiliation', args=[project.slug])
    return render(request, 'project/project_authors.html', {'project':project,
        'authors':authors, 'invitations':invitations,
        'affiliation_formset':affiliation_formset,
        'invite_author_form':invite_author_form,
        'corresponding_author_form':corresponding_author_form,
        'corresponding_email_form':corresponding_email_form,
        'add_item_url':edit_affiliations_url, 'remove_item_url':edit_affiliations_url,
        'is_submitting':is_submitting})


def edit_metadata_item(request, project_slug):
    """
    Function accessed via ajax for editing a project's related item
    in a formset.

    Either add the first form, or remove an item, returning the rendered
    template of the formset.

    Accessed by submitting authors during edit stage, or editor during
    copyedit stage

    """
    user = request.user
    project = ActiveProject.objects.filter(slug=project_slug)
    if project:
        project = project.get()
    else:
        raise Http404()

    is_submitting = bool(project.authors.filter(user=user, is_submitting=True))

    if not (is_submitting and project.author_editable()) and not (project.copyeditable() and user == project.editor):
        raise Http404()

    model_dict = {'reference': Reference, 'publication': Publication,
                  'topic': Topic}
    # Whether the item relation is generic
    is_generic_relation = {'reference': True, 'publication':True,
                           'topic': True}

    custom_formsets = {'reference':forms.ReferenceFormSet,
                       'publication':forms.PublicationFormSet,
                       'topic':forms.TopicFormSet}

    # The fields of each formset
    metadata_item_fields = {'reference': ('description',),
                            'publication': ('citation', 'url'),
                            'topic': ('description',)}

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
        ItemFormSet = inlineformset_factory(parent_model=ActiveProject,
            model=model, fields=metadata_item_fields[item], extra=extra_forms,
            max_num=custom_formsets[item].max_forms, can_delete=False,
            formset=custom_formsets[item], validate_max=True)

    formset = ItemFormSet(instance=project)
    edit_url = reverse('edit_metadata_item', args=[project.slug])

    return render(request, 'project/item_list.html',
            {'formset':formset, 'item':item, 'item_label':formset.item_label,
             'form_name':formset.form_name, 'add_item_url':edit_url,
             'remove_item_url':edit_url})


@project_auth(auth_mode=0, post_auth_mode=2)
def project_metadata(request, project_slug, **kwargs):
    """
    For editing project metadata
    """
    user, project, authors, is_submitting = (kwargs[k] for k in
        ('user', 'project', 'authors', 'is_submitting'))

    # There are several forms for different types of metadata
    ReferenceFormSet = generic_inlineformset_factory(Reference,
        fields=('description',), extra=0,
        max_num=forms.ReferenceFormSet.max_forms, can_delete=False,
        formset=forms.ReferenceFormSet, validate_max=True)

    description_form = forms.MetadataForm(resource_type=project.resource_type,
        instance=project)
    reference_formset = ReferenceFormSet(instance=project)

    if request.method == 'POST':
        description_form = forms.MetadataForm(
            resource_type=project.resource_type, data=request.POST,
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
        'messages':messages.get_messages(request),
        'is_submitting':is_submitting,
        'add_item_url':edit_url, 'remove_item_url':edit_url})


@project_auth(auth_mode=0, post_auth_mode=2)
def project_access(request, project_slug, **kwargs):
    """
    Page to edit project access policy

    """
    user, project = kwargs['user'], kwargs['project']

    if request.method == 'POST':
        access_form = forms.AccessMetadataForm(data=request.POST,
            instance=project)
        # The first validation is to check for valid access policy choice
        if access_form.is_valid():
            # The second validation is to check for valid license choice
            access_form.set_license_queryset(
                access_policy=access_form.cleaned_data['access_policy'])
            if access_form.is_valid():
                access_form.save()
                messages.success(request, 'Your access metadata has been updated.')
        else:
            messages.error(request,
                'Invalid submission. See errors below.')
    else:
        access_form = forms.AccessMetadataForm(instance=project)
        access_form.set_license_queryset(access_policy=project.access_policy)

    return render(request, 'project/project_access.html', {'project':project,
        'access_form':access_form, 'is_submitting':kwargs['is_submitting']})


def load_license(request, project_slug):
    """
    Reload the license input queryset with the right options for the
    access form's current access policy choice. Called via ajax.
    """
    user = request.user
    project = ActiveProject.objects.filter(slug=project_slug)
    if project:
        project = project.get()
    else:
        raise Http404()
    form = forms.AccessMetadataForm(instance=project)
    form.set_license_queryset(access_policy=int(request.GET['access_policy']))

    return render(request, 'project/license_input.html', {'form':form})



@project_auth(auth_mode=0, post_auth_mode=2)
def project_discovery(request, project_slug, **kwargs):
    """
    Page to edit external project discovery

    """
    project, is_submitting = (kwargs[k] for k in ('project',
        'is_submitting'))

    TopicFormSet = generic_inlineformset_factory(Topic,
        fields=('description',), extra=0, max_num=forms.TopicFormSet.max_forms,
        can_delete=False, formset=forms.TopicFormSet, validate_max=True)
    PublicationFormSet = generic_inlineformset_factory(Publication,
        fields=('citation', 'url'), extra=0,
        max_num=forms.PublicationFormSet.max_forms, can_delete=False,
        formset=forms.PublicationFormSet, validate_max=True)

    discovery_form = forms.DiscoveryForm(resource_type=project.resource_type,
        instance=project)
    publication_formset = PublicationFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    if request.method == 'POST':
        discovery_form = forms.DiscoveryForm(resource_type=project.resource_type,
            data=request.POST, instance=project)
        publication_formset = PublicationFormSet(request.POST,
                                                 instance=project)
        topic_formset = TopicFormSet(request.POST, instance=project)

        if discovery_form.is_valid() and publication_formset.is_valid() and topic_formset.is_valid():
            discovery_form.save()
            publication_formset.save()
            topic_formset.save()
            project.modified_datetime = timezone.now()
            project.save()
            messages.success(request, 'Your discovery information has been updated.')
            topic_formset = TopicFormSet(instance=project)
            publication_formset = PublicationFormSet(instance=project)
        else:
            messages.error(request, 'Invalid submission. See errors below.')
    edit_url = reverse('edit_metadata_item', args=[project.slug])
    return render(request, 'project/project_discovery.html',
        {'project':project, 'discovery_form':discovery_form,
         'publication_formset':publication_formset,
         'topic_formset':topic_formset, 'add_item_url':edit_url,
         'remove_item_url':edit_url, 'is_submitting':is_submitting})


class ProjectAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = PublishedProject.objects.all()

        if self.q:
            qs = qs.filter(title__icontains=self.q)

        return qs


def get_file_forms(project, subdir, display_dirs):
    """
    Get the file processing forms
    """
    upload_files_form = forms.UploadFilesForm(project=project)
    create_folder_form = forms.CreateFolderForm(project=project)
    rename_item_form = forms.RenameItemForm(project=project)
    move_items_form = forms.MoveItemsForm(project=project, subdir=subdir,
                                          display_dirs=display_dirs)
    delete_items_form = forms.DeleteItemsForm(project=project)

    return (upload_files_form, create_folder_form, rename_item_form,
            move_items_form, delete_items_form)

def get_project_file_info(project, subdir):
    """
    Get the files, directories, and breadcrumb info for a project's
    subdirectory.
    Helper function for generating the files panel
    """
    display_files = display_dirs = ()
    try:
        display_files, display_dirs = project.get_directory_content(
            subdir=subdir)
        file_error = None
    except (FileNotFoundError, ValidationError):
        file_error = 'Directory not found'
    except OSError:
        file_error = 'Unable to read directory'

    # Breadcrumbs
    dir_breadcrumbs = utility.get_dir_breadcrumbs(subdir)
    parent_dir = os.path.split(subdir)[0]

    return display_files, display_dirs, dir_breadcrumbs, parent_dir, file_error


def get_project_file_warning(display_files, display_dirs, subdir):
    """
    Check for invalid or otherwise problematic file names.
    """
    lower_names = {}
    bad_names = []
    case_conflicts = []
    for l in (display_dirs, display_files):
        for f in l:
            try:
                validate_filename(f.name)
            except ValidationError:
                bad_names.append(f.name)
            else:
                lower_name = f.name.lower()
                try:
                    other_name = lower_names[lower_name]
                    case_conflicts.append((other_name, f.name))
                except KeyError:
                    lower_names[lower_name] = f.name
    if bad_names or case_conflicts:
        text = 'One or more files must be renamed before publication:<ul>'
        if bad_names:
            text += '<li>'
            if len(bad_names) == 1:
                text += 'Invalid file name: '
            else:
                text += 'Invalid file names: '
            text += format_html_join(', ', '<strong>{}</strong>',
                                     ([n] for n in bad_names[0:4]))
            if len(bad_names) > 4:
                text += ', and {} more'.format(len(bad_names) - 4)
            text += '</li>'
        if case_conflicts:
            text += '<li>'
            text += 'Conflicting file names: '
            text += format_html('<strong>{}</strong> and <strong>{}</strong>',
                                case_conflicts[0][0], case_conflicts[0][1])
            if len(case_conflicts) > 1:
                text += ', and {} more'.format(len(case_conflicts) - 1)
        text += '</ul>'
        return text


@project_auth(auth_mode=2)
def project_files_panel(request, project_slug, **kwargs):
    """
    Return the file panel for the project, along with the forms used to
    manipulate them. Called via ajax to navigate directories.
    """
    project, is_submitting = (kwargs[k] for k in ('project', 'is_submitting'))
    is_editor = request.user == project.editor
    subdir = request.GET['subdir']

    if not request.is_ajax():
        return redirect('project_files', project_slug=project_slug)

    (display_files, display_dirs, dir_breadcrumbs, parent_dir,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    file_warning = get_project_file_warning(display_files, display_dirs,
                                              subdir)

    (upload_files_form, create_folder_form, rename_item_form,
     move_items_form, delete_items_form) = get_file_forms(
         project=project, subdir=subdir, display_dirs=display_dirs)

    return render(request, 'project/edit_files_panel.html',
        {'project':project, 'subdir':subdir, 'file_error':file_error,
         'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
         'display_files':display_files, 'display_dirs':display_dirs,
         'file_warning':file_warning,
         'upload_files_form':upload_files_form,
         'create_folder_form':create_folder_form,
         'rename_item_form':rename_item_form,
         'move_items_form':move_items_form,
         'delete_items_form':delete_items_form,
         'is_submitting':is_submitting,
         'is_editor':is_editor})

def process_items(request, form):
    """
    Process the file manipulation items with the appropriate form and
    action. Returns the working subdirectory.

    Helper function for `project_files`.
    """
    if form.is_valid():
        success_msg, errors = form.perform_action()
        if errors:
            messages.error(request, errors)
        else:
            messages.success(request, success_msg)
        return form.cleaned_data['subdir']
    else:
        messages.error(request, utility.get_form_errors(form))
        # If there are no errors with the subdir, keep the same subdir.
        if 'subdir' in form.cleaned_data:
            return form.cleaned_data['subdir']
        else:
            return ''

def process_files_post(request, project):
    """
    Helper function for `project_files`
    """
    if 'upload_files' in request.POST:
        form = forms.UploadFilesForm(project=project, data=request.POST,
            files=request.FILES)
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
        form = forms.DeleteItemsForm(project=project, data=request.POST)
        subdir = process_items(request, form)

    return subdir


@project_auth(auth_mode=0, post_auth_mode=2)
def project_files(request, project_slug, subdir='', **kwargs):
    "View and manipulate files in a project"
    project, is_submitting = (kwargs[k] for k in
        ('project', 'is_submitting'))

    if request.method == 'POST':
        if not is_submitting:
            raise Http404()

        if 'request_storage' in request.POST:
            storage_request_form = forms.StorageRequestForm(project=project,
                                                            data=request.POST)
            if storage_request_form.is_valid():
                storage_request_form.instance.project = project
                storage_request_form.save()
                messages.success(request, 'Your storage request has been received.')
            else:
                messages.error(request, utility.get_form_errors(storage_request_form))
        elif 'cancel_request' in request.POST:
            storage_request = StorageRequest.objects.filter(project=project,
                is_active=True)
            if storage_request:
                storage_request.get().delete()
                messages.success(request, 'Your storage request has been cancelled.')
        else:
            # process the file manipulation post
            subdir = process_files_post(request, project)
            project.modified_datetime = timezone.now()

    storage_info = project.get_storage_info()
    storage_request = StorageRequest.objects.filter(project=project,
                                                    is_active=True).first()
    # Forms
    storage_request_form = forms.StorageRequestForm(project=project) if (not storage_request and is_submitting) else None

    (display_files, display_dirs, dir_breadcrumbs, _,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    file_warning = get_project_file_warning(display_files, display_dirs,
                                              subdir)

    (upload_files_form, create_folder_form, rename_item_form,
     move_items_form, delete_items_form) = get_file_forms(
         project=project, subdir=subdir, display_dirs=display_dirs)

    return render(request, 'project/project_files.html', {'project':project,
        'individual_size_limit':utility.readable_size(
            ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT),
        'subdir':subdir, 'display_files':display_files,
        'display_dirs':display_dirs, 'storage_info':storage_info,
        'storage_request':storage_request,
        'storage_request_form':storage_request_form,
        'upload_files_form':upload_files_form,
        'create_folder_form':create_folder_form,
        'rename_item_form':rename_item_form, 'move_items_form':move_items_form,
        'delete_items_form':delete_items_form, 'is_submitting':is_submitting,
        'dir_breadcrumbs':dir_breadcrumbs, 'file_error':file_error,
        'file_warning':file_warning})


@project_auth(auth_mode=2)
def serve_active_project_file(request, project_slug, file_name, **kwargs):
    """
    Serve a file in an active project. file_name is file path relative
    to the project's file root.
    """
    file_path = os.path.join(kwargs['project'].file_root(), file_name)
    try:
        return serve_file(file_path)
    except IsADirectoryError:
        return redirect(request.path + '/')


@project_auth(auth_mode=2)
def preview_files_panel(request, project_slug, **kwargs):
    """
    Return the file panel for the project, along with the forms used to
    manipulate them. Called via ajax to navigate directories.
    """
    project = kwargs['project']
    subdir = request.GET['subdir']

    if not request.is_ajax():
        return redirect('project_preview', project_slug=project_slug)

    (display_files, display_dirs, dir_breadcrumbs, parent_dir,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    files_panel_url = reverse('preview_files_panel', args=(project.slug,))
    file_warning = get_project_file_warning(display_files, display_dirs,
                                              subdir)

    return render(request, 'project/files_panel.html',
        {'project':project, 'subdir':subdir, 'file_error':file_error,
         'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
         'display_files':display_files, 'display_dirs':display_dirs,
         'files_panel_url':files_panel_url, 'file_warning':file_warning})


@project_auth(auth_mode=2)
def project_preview(request, project_slug, subdir='', **kwargs):
    """
    Preview what the published project would look like. Includes
    serving files.

    """
    project, authors = (kwargs[k] for k in ('project', 'authors'))
    authors = project.get_author_info()
    invitations = project.authorinvitations.filter(is_active=True)
    corresponding_author = authors.get(is_corresponding=True)
    corresponding_author.text_affiliations = ', '.join(a.name for a in corresponding_author.affiliations.all())

    references = project.references.all()
    publication = project.publications.all().first()
    topics = project.topics.all()
    parent_projects = project.parent_projects.all()
    languages = project.programming_languages.all()

    passes_checks = project.check_integrity()

    if passes_checks:
        messages.success(request, 'The project has passed all automatic checks.')
    else:
        for e in project.integrity_errors:
            messages.error(request, e)

    (display_files, display_dirs, dir_breadcrumbs, _,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    files_panel_url = reverse('preview_files_panel', args=(project.slug,))
    file_warning = get_project_file_warning(display_files, display_dirs,
                                              subdir)

    return render(request, 'project/project_preview.html', {'project':project,
        'display_files':display_files, 'display_dirs':display_dirs,
        'authors':authors, 'corresponding_author':corresponding_author,
        'invitations':invitations, 'references':references,
        'publication':publication, 'topics':topics, 'languages':languages,
        'passes_checks':passes_checks, 'dir_breadcrumbs':dir_breadcrumbs,
        'files_panel_url':files_panel_url, 'subdir':subdir,
        'file_error':file_error, 'file_warning':file_warning,
        'parent_projects':parent_projects})


@project_auth(auth_mode=2)
def project_license_preview(request, project_slug, **kwargs):
    """
    View a project's license
    """
    project = kwargs['project']
    license = project.license
    license_content = project.license_content(fmt='html')

    return render(request, 'project/project_license_preview.html',
        {'project':project, 'license':license,
        'license_content':license_content})


@project_auth(auth_mode=0)
def project_proofread(request, project_slug, **kwargs):
    """
    Proofreading page for project before submission
    """
    return render(request, 'project/project_proofread.html',
        {'project':kwargs['project']})


@project_auth(auth_mode=0)
def check_integrity(request, project_slug, **kwargs):
    """
    Check whether a project is submittable. Called via ajax
    """
    project = kwargs['project']
    result = project.check_integrity()

    return JsonResponse({'passes_checks':result,
        'integrity_errors':project.integrity_errors})


@project_auth(auth_mode=0)
def project_submission(request, project_slug, **kwargs):
    """
    View submission details regarding a project, submit the project
    for review, cancel a submission, approve a submission, and withdraw
    approval.
    """
    user, project, authors, is_submitting = (kwargs[k] for k in
        ('user', 'project', 'authors', 'is_submitting'))

    author_comments_form = forms.AuthorCommentsForm() if is_submitting and project.author_editable() else None

    if request.method == 'POST':
        # ActiveProject is submitted for review
        if 'submit_project' in request.POST and is_submitting:
            author_comments_form = forms.AuthorCommentsForm(data=request.POST)
            if project.is_submittable() and author_comments_form.is_valid():
                project.submit(author_comments=author_comments_form.cleaned_data['author_comments'])
                notification.submit_notify(project)
                messages.success(request, 'Your project has been submitted. You will be notified when an editor is assigned.')
            else:
                messages.error(request, 'Fix the errors before submitting')
        elif 'resubmit_project' in request.POST and is_submitting:
            author_comments_form = forms.AuthorCommentsForm(data=request.POST)
            if project.is_resubmittable() and author_comments_form.is_valid():
                project.resubmit(author_comments=author_comments_form.cleaned_data['author_comments'])
                notification.resubmit_notify(project)
                messages.success(request, 'Your project has been resubmitted. You will be notified when the editor makes their decision.')
        # Author approves publication
        elif 'approve_publication' in request.POST:
            author = authors.get(user=user)
            # Register the approval if valid
            if project.approve_author(author):
                if project.submission_status == 60:
                    messages.success(request, 'You have approved the publication of your project. The editor will publish it shortly')
                    notification.authors_approved_notify(request, project)
                else:
                    messages.success(request, 'You have approved the publication of your project.')
                authors = project.authors.all().order_by('display_order')
            else:
                messages.error(request, 'Invalid')

    # Whether the submission is currently waiting for the user to approve
    awaiting_user_approval = False
    if project.under_submission():
        edit_logs = project.edit_logs.all()
        copyedit_logs = project.copyedit_logs.all()
        for e in edit_logs:
            e.set_quality_assurance_results()
        # Awaiting authors
        if project.submission_status == 50:
            authors = authors.order_by('approval_datetime')
            for a in authors:
                a.set_display_info()
                if user == a.user and not a.approval_datetime:
                    awaiting_user_approval = True
    else:
        edit_logs, copyedit_logs = None, None

    return render(request, 'project/project_submission.html', {
        'project':project, 'authors':authors,
        'is_submitting':is_submitting, 'author_comments_form':author_comments_form,
        'edit_logs':edit_logs, 'copyedit_logs':copyedit_logs,
        'awaiting_user_approval':awaiting_user_approval})


def rejected_submission_history(request, project_slug):
    """
    Submission history for a rejected project
    """
    user = request.user
    project = ArchivedProject.objects.filter(slug=project_slug, archive_reason=3)
    if project:
        project = project.get()
    else:
        raise Http404()
    if user.is_admin or project.authors.filter(user=user):
        edit_logs = project.edit_logs.all()
        for e in edit_logs:
            e.set_quality_assurance_results()
        copyedit_logs = project.copyedit_logs.all()

        return render(request, 'project/rejected_submission_history.html',
            {'project':project, 'edit_logs':edit_logs,
             'copyedit_logs':copyedit_logs})


def published_versions(request, project_slug):
    """
    List of published versions of a project. Viewable by admins and
    authors.
    """
    user = request.user
    # Account for different authors between versions
    if user.is_admin:
        projects = PublishedProject.objects.filter(slug=project_slug).order_by('version_order')
    else:
        authors = PublishedAuthor.objects.filter(user=user, project__slug=project_slug).order_by('project__version_order')
        projects = [a.project for a in authors]
        # Not an author of this project set
        if not projects:
            return redirect('project_home')

    return render(request, 'project/published_versions.html',
        {'projects':projects, 'first_project':projects[0],
         'current_site':get_current_site(request)})


def published_submission_history(request, project_slug, version):
    """
    Submission history for a published project
    """
    user = request.user
    project = PublishedProject.objects.filter(slug=project_slug, version=version)
    if project:
        project = project.get()
    else:
        raise Http404()
    if user.is_admin or project.authors.filter(user=user):
        edit_logs = project.edit_logs.all()
        for e in edit_logs:
            e.set_quality_assurance_results()
        copyedit_logs = project.copyedit_logs.all()

        return render(request, 'project/published_submission_history.html',
            {'project':project, 'edit_logs':edit_logs,
             'copyedit_logs':copyedit_logs, 'published':True})


def published_files_panel(request, project_slug, version):
    """
    Return the main file panel for the published project, for all access
    policies. Called via ajax.
    """
    project = PublishedProject.objects.filter(slug=project_slug,
        version=version)
    if project:
        project = project.get()
    else:
        raise Http404()

    subdir = request.GET.get('subdir')
    if subdir is None:
        raise Http404()

    if not request.is_ajax():
        return redirect('published_project', project_slug=project_slug,
            version=version)

    if project.has_access(request.user):
        (display_files, display_dirs, dir_breadcrumbs, parent_dir,
         file_error) = get_project_file_info(project=project, subdir=subdir)

        files_panel_url = reverse('published_files_panel',
            args=(project.slug, project.version))

        return render(request, 'project/files_panel.html',
            {'project':project, 'subdir':subdir,
             'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
             'display_files':display_files, 'display_dirs':display_dirs,
             'files_panel_url':files_panel_url, 'file_error':file_error})
    else:
        raise Http404()


def serve_published_project_file(request, project_slug, version,
        full_file_name):
    """
    Serve a file of a published project.
    Works for open and protected. Not needed for open.

    """
    try:
        project = PublishedProject.objects.get(slug=project_slug,
            version=version)
    except ObjectDoesNotExist:
        raise Http404()
    if project.has_access(request.user):
        file_path = os.path.join(project.file_root(), full_file_name)
        try:
            return serve_file(file_path)
        except IsADirectoryError:
            return redirect(request.path + '/')
        except FileNotFoundError:
            raise Http404()
    raise PermissionDenied()


def serve_published_project_zip(request, project_slug, version):
    """
    Serve the zip file of a published project.
    Works for open and protected. Not needed for open.

    """
    try:
        project = PublishedProject.objects.get(slug=project_slug,
            version=version)
    except ObjectDoesNotExist:
        raise Http404()
    if project.has_access(request.user):
        try:
            return serve_file(project.zip_name(full=True))
        except FileNotFoundError:
            raise Http404()
    raise PermissionDenied()


def published_project_license(request, project_slug, version):
    """
    Displays a published project's license
    """
    try:
        project = PublishedProject.objects.get(slug=project_slug,
            version=version)
    except ObjectDoesNotExist:
        raise Http404()
    license = project.license
    license_content = project.license_content(fmt='html')

    return render(request, 'project/published_project_license.html',
        {'project':project, 'license':license,
        'license_content':license_content})


def published_project_latest(request, project_slug):
    """
    Redirect to latest project version
    """
    try:
        version = PublishedProject.objects.get(slug=project_slug,
            is_latest_version=True).version
    except ObjectDoesNotExist:
        raise Http404()
    return redirect('published_project', project_slug=project_slug,
        version=version)


def published_project(request, project_slug, version, subdir=''):
    """
    Displays a published project
    """
    try:
        project = PublishedProject.objects.get(slug=project_slug,
                                               version=version)
    except ObjectDoesNotExist:
        raise Http404()

    authors = project.authors.all().order_by('display_order')
    for a in authors:
        a.set_display_info()
    references = project.references.all()
    publication = project.publications.all().first()
    topics = project.topics.all()
    languages = project.programming_languages.all()
    contact = project.contact
    news = project.news.all().order_by('-publish_datetime')
    parent_projects = project.parent_projects.all()
    # derived_projects = project.derived_publishedprojects.all()

    has_access = project.has_access(request.user)
    current_site = get_current_site(request)
    all_project_versions = PublishedProject.objects.filter(
        slug=project_slug).order_by('version_order')
    context = {'project': project, 'authors': authors,
               'references': references, 'publication': publication,
               'topics': topics, 'languages': languages, 'contact': contact,
               'has_access': has_access, 'current_site': current_site,
               'news': news, 'all_project_versions': all_project_versions,
               'parent_projects':parent_projects}

    # The file and directory contents
    if has_access:
        (display_files, display_dirs, dir_breadcrumbs, parent_dir,
         file_error) = get_project_file_info(project=project, subdir=subdir)
        if file_error:
            status = 404
        else:
            status = 200

        main_size, compressed_size = [utility.readable_size(s) for s in
            (project.main_storage_size, project.compressed_storage_size)]
        files_panel_url = reverse('published_files_panel',
            args=(project.slug, project.version))

        context = {**context, **{'dir_breadcrumbs':dir_breadcrumbs,
            'main_size':main_size, 'compressed_size':compressed_size,
            'display_files':display_files, 'display_dirs':display_dirs,
            'files_panel_url':files_panel_url, 'subdir':subdir,
            'file_error':file_error}}
    elif subdir:
        status = 403
    else:
        status = 200

    return render(request, 'project/published_project.html', context,
                  status=status)


@login_required
def sign_dua(request, project_slug, version):
    """
    Page to sign the dua for a protected project.
    Both restricted and credentialed policies.
    """
    user = request.user
    project = PublishedProject.objects.filter(slug=project_slug, version=version)
    if project:
        project = project.get()
    else:
        raise Http404()

    if project.deprecated_files or not project.access_policy or project.has_access(user):
        return redirect('published_project',
                        project_slug=project_slug, version=version)

    if project.access_policy == 2 and not user.is_credentialed:
        return render(request, 'project/credential_required.html')

    license = project.license
    license_content = project.license_content(fmt='html')

    if request.method == 'POST' and 'agree' in request.POST:
        project.approved_users.add(user)
        DUASignature.objects.create(user=user, project=project)
        # Add all the emails affiliated with the user to the bucket
        if GCP.objects.filter(project=project.id) and project.gcp.bucket_name:
            email_list = user.get_emails()
            for email in email_list:
                add_email_bucket_access(project, email)
        return render(request, 'project/sign_dua_complete.html', {
            'project':project})

    return render(request, 'project/sign_dua.html', {'project':project,
        'license':license, 'license_content':license_content})
