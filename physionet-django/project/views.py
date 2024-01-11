import datetime as dt
import logging
import os

import notification.utility as notification
from dal import autocomplete
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms import inlineformset_factory, modelformset_factory
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from physionet.forms import set_saved_fields_cookie
from physionet.middleware.maintenance import ServiceUnavailable
from physionet.storage import generate_signed_url_helper
from physionet.utility import serve_file
from project import forms, utility
from project.fileviews import display_project_file
from project.models import (
    AccessPolicy,
    AccessLog,
    ActiveProject,
    Affiliation,
    AnonymousAccess,
    Author,
    AuthorInvitation,
    DataAccess,
    DataAccessRequest,
    DataAccessRequestReviewer,
    DUASignature,
    GCPLog,
    DUA,
    Publication,
    PublishedAuthor,
    PublishedProject,
    Reference,
    StorageRequest,
    SubmissionStatus,
    Topic,
    UploadedDocument,
)
from project.authorization.access import can_view_project_files, can_access_project
from project.projectfiles import ProjectFiles
from project.validators import validate_filename, validate_gcs_bucket_object
from user.forms import AssociatedEmailChoiceForm
from user.models import CloudInformation, CredentialApplication, LegacyCredential, User, Training
from project.cloud.s3 import (
    has_s3_credentials,
    files_sent_to_S3,
)
from django.db.models import F, DateTimeField, ExpressionWrapper

LOGGER = logging.getLogger(__name__)

def project_auth(auth_mode=0, post_auth_mode=0):
    """
    Authorization decorator for project. Also adds project information
    to kwargs.

    auth_mode is one of the following:
    - 0 : the user must be an author.
    - 1 : the user must be the submitting author.
    - 2 : the user must be an author or have permission to edit all ActiveProjects.
    - 3 : the user must be an author or have permission to edit all ActiveProjects.
          or be authenticated with a passphrase

    post_auth_mode is one of the following and applies only to post:
    - 0 : no additional check
    - 1 : the user must be an author, and the project must be in one of
          its author editable stages.
    - 2 : the user must be the submitting author, and the project must
          be in one of its author editable stages.
    """
    def real_decorator(base_view):
        def view_wrapper(request, *args, **kwargs):
            # Verify project
            try:
                project = ActiveProject.objects.get(
                    slug=kwargs['project_slug'])
            except ObjectDoesNotExist:
                raise PermissionDenied()

            # Authenticate passphrase for anonymous access
            an_url = request.get_signed_cookie('anonymousaccess', None, max_age=60*60)
            has_passphrase = project.get_anonymous_url() == an_url

            # Get user
            user = request.user

            # Requires login if passphrase is non-existent
            if not has_passphrase and not user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            # Verify user's role in project
            authors = project.authors.all().order_by('display_order')
            is_author = not user.is_anonymous and bool(authors.filter(user=user))
            is_submitting = (user == authors.get(is_submitting=True).user)

            # Authentication
            if auth_mode == 0:
                allow = is_author
            elif auth_mode == 1:
                allow = is_submitting
            elif auth_mode == 2:
                allow = is_author or user.has_perm('project.change_activeproject')
            elif auth_mode == 3:
                allow = has_passphrase or is_author or user.has_perm('project.change_activeproject')
            else:
                allow = False

            # Authors cannot view archived projects
            if (
                project.submission_status == SubmissionStatus.ARCHIVED
                and not user.has_perm("project.change_activeproject")
            ):
                allow = False

            # Post authentication
            if request.method == 'POST':
                if post_auth_mode == 1:
                    allow = is_author and project.author_editable()
                elif post_auth_mode == 2:
                    allow = is_submitting and project.author_editable()

            # Render
            if allow:
                kwargs['user'] = user
                kwargs['project'] = project
                kwargs['authors'] = authors
                kwargs['is_author'] = is_author
                kwargs['is_submitting'] = is_submitting
                kwargs['has_passphrase'] = has_passphrase
                return base_view(request, *args, **kwargs)
            raise PermissionDenied()
        return view_wrapper
    return real_decorator


def process_invitation_response(request, invitation_response_formset):
    """
    Process an invitation response.
    Helper function to view: project_home

    If an invitation was accepted, return the ActiveProject.
    Otherwise return None.
    """
    user = request.user
    invitation_id = int(request.POST['invitation_response'])
    for invitation_response_form in invitation_response_formset:
        # Only process the response that was submitted
        if invitation_response_form.instance.id == invitation_id:
            break
    else:
        return None

    invitation_response_form.user = user

    if invitation_response_form.is_valid():
        with transaction.atomic():
            # Update this invitation, and any other one made to the
            # same user, project, and invitation type
            invitation = invitation_response_form.instance
            project = invitation.project
            invitations = AuthorInvitation.objects.filter(
                is_active=True,
                email__in=user.get_emails(),
                project=project,
            )
            affected_emails = [i.email for i in invitations]
            invitations.update(
                response=invitation.response,
                response_datetime=timezone.now(),
                is_active=False,
            )
            # Create a new Author object
            if invitation.response:
                author = Author.objects.create(
                    project=project,
                    user=user,
                    display_order=project.authors.count() + 1,
                    corresponding_email=user.get_primary_email(),
                )
                Affiliation.objects.create(
                    author=author,
                    name=invitation_response_form.cleaned_data['affiliation'],
                )

            notification.invitation_response_notify(invitation,
                                                    affected_emails)
            messages.success(
                request,
                'The invitation has been {0}.'.format(
                    notification.RESPONSE_ACTIONS[invitation.response])
            )
            if invitation.response:
                return project
            else:
                return None
    else:
        # form is not valid
        messages.error(request,
                       utility.get_form_errors(invitation_response_form))
        return None


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

    request_reviewers = DataAccessRequestReviewer.objects.filter(reviewer=user,
                                                                 is_revoked=False,
                                                                 project__is_latest_version=True)

    published_projects = PublishedProject.objects.filter(authors__user=user,
                                                         is_latest_version=True).order_by("-publish_datetime")

    # Get the various projects.
    published_projects = [a for a in published_projects] + [a.project for a in request_reviewers]
    for p in published_projects:
        p.new_button = p.can_publish_new(user)
        p.requests_button = p.can_approve_requests(user)
        p.manage_reviewers_button = p.can_manage_data_access_reviewers(user)

    if request.method == 'POST' and 'invitation_response' in request.POST.keys():
        author_qs = AuthorInvitation.get_user_invitations(user)
        invitation_response_formset = InvitationResponseFormSet(request.POST,
                                                                queryset=author_qs)
        project = process_invitation_response(request,
                                              invitation_response_formset)
        if project:
            return redirect('project_authors', project_slug=project.slug)

    pending_author_approvals = []
    missing_affiliations = []
    pending_revisions = []

    active_projects = ActiveProject.objects.filter(authors__user=user).exclude(
        submission_status=SubmissionStatus.ARCHIVED).order_by("-creation_datetime")

    for p in active_projects:
        if (p.submission_status == SubmissionStatus.NEEDS_APPROVAL
                and not p.all_authors_approved()):
            if p.authors.get(user=user).is_submitting:
                pending_author_approvals.append(p)
            elif not p.authors.get(user=user).approval_datetime:
                pending_author_approvals.append(p)
        if (p.submission_status == SubmissionStatus.NEEDS_RESUBMISSION
                and p.authors.get(user=user).is_submitting):
            pending_revisions.append(p)
        if p.submission_status == SubmissionStatus.UNSUBMITTED and p.authors.get(user=user).affiliations.count() == 0:
            missing_affiliations.append([p, p.authors.get(user=user).creation_date])

    archived_projects = ActiveProject.objects.filter(
        authors__user=user, submission_status=SubmissionStatus.ARCHIVED).order_by("-creation_datetime")

    invitation_response_formset = InvitationResponseFormSet(
        queryset=AuthorInvitation.get_user_invitations(user))
    invitation_response_formset.form_kwargs['initial'] = {
        'affiliation': user.profile.affiliation
    }

    data_access_requests = DataAccessRequest.objects.filter(
        project__in=[p for p in published_projects if p.can_approve_requests(user)],
        status=0)

    return render(
        request,
        'project/project_home.html',
        {
            'projects': active_projects,
            'published_projects': published_projects,
            'archived_projects': archived_projects,
            'missing_affiliations': missing_affiliations,
            'pending_author_approvals': pending_author_approvals,
            'invitation_response_formset': invitation_response_formset,
            'data_access_requests': data_access_requests,
            'pending_revisions': pending_revisions,
        },
    )


@login_required
def create_project(request):
    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        raise ServiceUnavailable()

    user = request.user

    # Filter ActiveProject instances (excluding ARCHIVED)
    # Get Author objects related to these ActiveProjects
    active_projects = ActiveProject.objects.exclude(submission_status=SubmissionStatus.ARCHIVED)
    n_submitting = Author.objects.filter(
        user=user,
        is_submitting=True,
        content_type=ContentType.objects.get_for_model(ActiveProject),
        object_id__in=active_projects.values_list('id', flat=True)
    ).count()

    if n_submitting >= settings.MAX_SUBMITTABLE_PROJECTS:
        return render(
            request,
            "project/project_limit_reached.html",
            {"max_projects": settings.MAX_SUBMITTABLE_PROJECTS},
        )

    if request.method == 'POST':
        form = forms.CreateProjectForm(user=user, data=request.POST)
        if form.is_valid():
            project = form.save()
            response = redirect('project_overview', project_slug=project.slug)
            set_saved_fields_cookie(form, request.path, response)
            return response
    else:
        form = forms.CreateProjectForm(user=user)

    return render(request, 'project/create_project.html', {'form':form})

@login_required
def new_project_version(request, project_slug):
    """
    Publish a new version of a project

    """
    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        raise ServiceUnavailable()

    user = request.user

    # Filter ActiveProject instances (excluding ARCHIVED)
    # Get Author objects related to these ActiveProjects
    active_projects = ActiveProject.objects.exclude(submission_status=SubmissionStatus.ARCHIVED)
    n_submitting = Author.objects.filter(
        user=user,
        is_submitting=True,
        content_type=ContentType.objects.get_for_model(ActiveProject),
        object_id__in=active_projects.values_list('id', flat=True)
    ).count()

    if n_submitting >= settings.MAX_SUBMITTABLE_PROJECTS:
        return render(
            request,
            "project/project_limit_reached.html",
            {"max_projects": settings.MAX_SUBMITTABLE_PROJECTS},
        )

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
        project.archive(archive_reason=1, clear_files=True)
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

    if project.submission_status not in [SubmissionStatus.UNSUBMITTED, SubmissionStatus.NEEDS_RESUBMISSION]:
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
        transfer_author_form = forms.TransferAuthorForm(
            project=project)
    else:
        invite_author_form, corresponding_author_form, transfer_author_form = None, None, None

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
        elif 'transfer_author' in request.POST and is_submitting:
            transfer_author_form = forms.TransferAuthorForm(
                project=project, data=request.POST)
            if transfer_author_form.is_valid():
                transfer_author_form.transfer()
                notification.notify_submitting_author(request, project)
                messages.success(request, 'The submitting author has been updated.')
                return redirect('project_authors', project_slug=project.slug)
            else:
                messages.error(request, 'Submission unsuccessful. See form for errors.')

    authors = project.get_author_info()
    invitations = project.authorinvitations.filter(is_active=True)
    edit_affiliations_url = reverse('edit_affiliation', args=[project.slug])
    return render(
        request,
        "project/project_authors.html",
        {
            "project": project,
            "authors": authors,
            "invitations": invitations,
            "affiliation_formset": affiliation_formset,
            "invite_author_form": invite_author_form,
            "corresponding_author_form": corresponding_author_form,
            "corresponding_email_form": corresponding_email_form,
            "transfer_author_form": transfer_author_form,
            "add_item_url": edit_affiliations_url,
            "remove_item_url": edit_affiliations_url,
            "is_submitting": is_submitting,
        },
    )


def edit_content_item(request, project_slug):
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
    content_item_fields = {'reference': ('description',),
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
            fields=content_item_fields[item], extra=extra_forms,
            max_num=custom_formsets[item].max_forms, can_delete=False,
            formset=custom_formsets[item], validate_max=True)
    else:
        ItemFormSet = inlineformset_factory(parent_model=ActiveProject,
            model=model, fields=content_item_fields[item], extra=extra_forms,
            max_num=custom_formsets[item].max_forms, can_delete=False,
            formset=custom_formsets[item], validate_max=True)

    formset = ItemFormSet(instance=project)
    edit_url = reverse('edit_content_item', args=[project.slug])

    return render(request, 'project/item_list.html',
            {'formset':formset, 'item':item, 'item_label':formset.item_label,
             'form_name':formset.form_name, 'add_item_url':edit_url,
             'remove_item_url':edit_url})


@project_auth(auth_mode=0, post_auth_mode=2)
def project_content(request, project_slug, **kwargs):
    """
    For editing project content
    """
    user, project, authors, is_submitting = (kwargs[k] for k in
        ('user', 'project', 'authors', 'is_submitting'))

    if is_submitting and project.author_editable():
        editable = True
    else:
        editable = False

    # There are several forms for different types of content
    ReferenceFormSet = generic_inlineformset_factory(Reference,
        fields=('description',), extra=0,
        max_num=forms.ReferenceFormSet.max_forms, can_delete=False,
        formset=forms.ReferenceFormSet, validate_max=True)

    description_form = forms.ContentForm(resource_type=project.resource_type.id,
                                         instance=project, editable=editable)
    reference_formset = ReferenceFormSet(instance=project)
    saved = False

    if request.method == 'POST':
        description_form = forms.ContentForm(
            resource_type=project.resource_type.id, data=request.POST,
            instance=project, editable=editable)
        reference_formset = ReferenceFormSet(request.POST, instance=project)
        if description_form.is_valid() and reference_formset.is_valid():
            saved = True
            description_form.save()
            reference_formset.save()
            messages.success(request, 'Your project content has been updated.')
            reference_formset = ReferenceFormSet(instance=project)
        else:
            messages.error(request,
                'Invalid submission. See errors below.')
    edit_url = reverse('edit_content_item', args=[project.slug])

    response = render(request, 'project/project_content.html', {'project':project,
        'description_form':description_form, 'reference_formset':reference_formset,
        'messages':messages.get_messages(request),
        'is_submitting':is_submitting,
        'add_item_url':edit_url, 'remove_item_url':edit_url})
    if saved:
        set_saved_fields_cookie(description_form, request.path, response)
    return response


@project_auth(auth_mode=0, post_auth_mode=2)
def project_access(request, project_slug, **kwargs):
    """
    Page to edit project access policy

    """
    user, project, passphrase = kwargs['user'], kwargs['project'], ''
    is_submitting = kwargs['is_submitting']

    if is_submitting and project.author_editable():
        editable = True
    else:
        editable = False

    if request.method == 'POST':
        access_form = forms.AccessMetadataForm(data=request.POST, instance=project, editable=editable)
        if access_form.is_valid():
            access_form.save()
            messages.success(request, 'Your access metadata has been updated.')
        else:
            messages.error(request, 'Invalid submission. See errors below.')
    else:
        access_policy = request.GET.get('accessPolicy')
        if access_policy:
            access_form = forms.AccessMetadataForm(
                instance=project, editable=editable, access_policy=int(access_policy)
            )
        else:
            access_form = forms.AccessMetadataForm(instance=project, editable=editable)


    return render(request, 'project/project_access.html', {'project':project,
        'access_form':access_form, 'is_submitting':kwargs['is_submitting']})


@project_auth(auth_mode=0, post_auth_mode=2)
def project_discovery(request, project_slug, **kwargs):
    """
    Page to edit external project discovery

    """
    project, is_submitting = (kwargs[k] for k in ('project',
        'is_submitting'))

    if is_submitting and project.author_editable():
        editable = True
    else:
        editable = False

    TopicFormSet = generic_inlineformset_factory(Topic,
        fields=('description',), extra=0, max_num=forms.TopicFormSet.max_forms,
        can_delete=False, formset=forms.TopicFormSet, validate_max=True)
    PublicationFormSet = generic_inlineformset_factory(Publication,
        fields=('citation', 'url'), extra=0,
        max_num=forms.PublicationFormSet.max_forms, can_delete=False,
        formset=forms.PublicationFormSet, validate_max=True)

    discovery_form = forms.DiscoveryForm(
        resource_type=project.resource_type.id,
        instance=project, editable=editable)
    publication_formset = PublicationFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    if request.method == 'POST':
        discovery_form = forms.DiscoveryForm(
            resource_type=project.resource_type.id, data=request.POST,
            instance=project, editable=editable)
        publication_formset = PublicationFormSet(request.POST,
                                                 instance=project)
        topic_formset = TopicFormSet(request.POST, instance=project)

        if discovery_form.is_valid() and publication_formset.is_valid() and topic_formset.is_valid():
            discovery_form.save()
            publication_formset.save()
            topic_formset.save()
            messages.success(request, 'Your discovery information has been updated.')
            topic_formset = TopicFormSet(instance=project)
            publication_formset = PublicationFormSet(instance=project)
        else:
            messages.error(request, 'Invalid submission. See errors below.')
    edit_url = reverse('edit_content_item', args=[project.slug])
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

    if is_submitting and project.author_editable():
        files_editable = True
    elif is_editor and project.copyeditable():
        files_editable = True
    else:
        files_editable = False

    (display_files, display_dirs, dir_breadcrumbs, parent_dir,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    file_warning = get_project_file_warning(display_files, display_dirs,
                                              subdir)

    storage_info = project.get_storage_info()

    (upload_files_form, create_folder_form, rename_item_form,
     move_items_form, delete_items_form) = get_file_forms(
         project=project, subdir=subdir, display_dirs=display_dirs)

    return render(
        request,
        'project/edit_files_panel.html',
        {
            'project': project,
            'subdir': subdir,
            'file_error': file_error,
            'dir_breadcrumbs': dir_breadcrumbs,
            'parent_dir': parent_dir,
            'display_files': display_files,
            'display_dirs': display_dirs,
            'file_warning': file_warning,
            'storage_type': settings.STORAGE_TYPE,
            'storage_info': storage_info,
            'upload_files_form': upload_files_form,
            'create_folder_form': create_folder_form,
            'rename_item_form': rename_item_form,
            'move_items_form': move_items_form,
            'delete_items_form': delete_items_form,
            'is_submitting': is_submitting,
            'is_editor': is_editor,
            'files_editable': files_editable,
            'individual_size_limit': utility.readable_size(ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT),
        },
    )


def process_items(request, form):
    """
    Process the file manipulation items with the appropriate form and
    action. Returns the working subdirectory.

    Helper function for `project_files`.
    """
    if form.is_valid():
        success_msg, errors = form.perform_action()
        form.project.content_modified()
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
    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        raise ServiceUnavailable()

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
                notification.storage_request_notify(request, project)
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

    if is_submitting and project.author_editable():
        files_editable = True
    else:
        files_editable = False

    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        maintenance_message = settings.SYSTEM_MAINTENANCE_MESSAGE or (
            "The site is currently undergoing maintenance, and project "
            "files cannot be edited.  Please try again later."
        )
        files_editable = False
    else:
        maintenance_message = None

    storage_info = project.get_storage_info()
    storage_request = StorageRequest.objects.filter(project=project,
                                                    is_active=True).first()
    # Forms
    storage_request_form = (
        forms.StorageRequestForm(project=project) if (not storage_request and is_submitting) else None
    )

    (display_files, display_dirs, dir_breadcrumbs, parent_dir,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    file_warning = get_project_file_warning(display_files, display_dirs, subdir)

    (upload_files_form, create_folder_form, rename_item_form,
     move_items_form, delete_items_form) = get_file_forms(
         project=project, subdir=subdir, display_dirs=display_dirs)

    return render(
        request,
        'project/project_files.html',
        {
            'project': project,
            'individual_size_limit': utility.readable_size(ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT),
            'subdir': subdir,
            'parent_dir': parent_dir,
            'display_files': display_files,
            'display_dirs': display_dirs,
            'storage_info': storage_info,
            'storage_request': storage_request,
            'storage_request_form': storage_request_form,
            'upload_files_form': upload_files_form,
            'create_folder_form': create_folder_form,
            'rename_item_form': rename_item_form,
            'move_items_form': move_items_form,
            'delete_items_form': delete_items_form,
            'is_submitting': is_submitting,
            'dir_breadcrumbs': dir_breadcrumbs,
            'file_error': file_error,
            'file_warning': file_warning,
            'files_editable': files_editable,
            'maintenance_message': maintenance_message,
            'is_lightwave_supported': project.files.is_lightwave_supported(),
            'storage_type': settings.STORAGE_TYPE,
        },
    )


@project_auth(auth_mode=3)
def serve_active_project_file(request, project_slug, file_name, **kwargs):
    """
    Serve a file in an active project. file_name is file path relative
    to the project's file root.
    """
    file_path = os.path.join(kwargs['project'].file_root(), file_name)
    try:
        attach = ('download' in request.GET)

        # Temporary workaround: Chromium doesn't permit viewing PDF
        # files in sandboxed mode:
        # https://bugs.chromium.org/p/chromium/issues/detail?id=271452
        # Until this is fixed, disable CSP sandbox for PDF files when
        # viewed by the authors.
        if file_path.endswith('.pdf') and kwargs['is_author']:
            sandbox = False
        else:
            sandbox = True

        return serve_file(file_path, attach=attach, sandbox=sandbox)
    except IsADirectoryError:
        return redirect(request.path + '/')


@project_auth(auth_mode=3)
def display_active_project_file(request, project_slug, file_name, **kwargs):
    """
    Display a file in an active project. file_name is file path relative
    to the project's file root.
    """
    return display_project_file(request, kwargs['project'], file_name)


@project_auth(auth_mode=3)
def preview_files_panel(request, project_slug, **kwargs):
    """
    Return the file panel for the project, along with the forms used to
    manipulate them. Called via ajax to navigate directories.
    """
    project = kwargs['project']
    subdir = request.GET['subdir']

    (display_files, display_dirs, dir_breadcrumbs, parent_dir,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    files_panel_url = reverse('preview_files_panel', args=(project.slug,))
    file_warning = get_project_file_warning(display_files, display_dirs,
                                              subdir)

    if request.GET.get('v', '1') == '1':
        template = 'project/files_panel.html'
    else:
        template = 'project/files_panel_v2.html'

    return render(request, template,
        {'project':project, 'subdir':subdir, 'file_error':file_error,
         'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
         'display_files':display_files, 'display_dirs':display_dirs,
         'files_panel_url':files_panel_url, 'file_warning':file_warning})


@project_auth(auth_mode=3)
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

    references = project.references.all().order_by('order')
    publication = project.publications.all().first()
    topics = project.topics.all()
    parent_projects = project.parent_projects.all()
    languages = project.programming_languages.all()
    citations = project.citation_text_all()
    platform_citations = project.get_platform_citation()
    show_platform_wide_citation = any(platform_citations.values())
    main_platform_citation = next((item for item in platform_citations.values() if item is not None), '')
    passes_checks = project.check_integrity()

    if passes_checks:
        messages.success(request, 'The project has passed all automatic checks.')
    else:
        for e in project.integrity_errors:
            messages.error(request, e)

    (display_files, display_dirs, dir_breadcrumbs, parent_dir,
     file_error) = get_project_file_info(project=project, subdir=subdir)
    files_panel_url = reverse('preview_files_panel', args=(project.slug,))
    file_warning = get_project_file_warning(display_files, display_dirs, subdir)

    # Flag for anonymous access
    has_passphrase = kwargs['has_passphrase']

    return render(
        request,
        'project/project_preview.html',
        {
            'project': project,
            'display_files': display_files,
            'display_dirs': display_dirs,
            'authors': authors,
            'corresponding_author': corresponding_author,
            'invitations': invitations,
            'references': references,
            'publication': publication,
            'topics': topics,
            'languages': languages,
            'passes_checks': passes_checks,
            'dir_breadcrumbs': dir_breadcrumbs,
            'files_panel_url': files_panel_url,
            'citations': citations,
            'subdir': subdir,
            'parent_dir': parent_dir,
            'file_error': file_error,
            'file_warning': file_warning,
            'platform_citations': platform_citations,
            'parent_projects': parent_projects,
            'has_passphrase': has_passphrase,
            'is_lightwave_supported': project.files.is_lightwave_supported(),
            'show_platform_wide_citation': show_platform_wide_citation,
            'main_platform_citation': main_platform_citation,
        },
    )


@project_auth(auth_mode=3)
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


@project_auth(auth_mode=3)
def project_required_trainings_preview(request, project_slug, **kwargs):
    """
    View a project's license
    """
    project = kwargs['project']
    required_trainings = project.required_trainings.all()

    return render(
        request,
        'project/project_required_trainings_preview.html',
        {'project': project, 'required_trainings': required_trainings},
    )


@project_auth(auth_mode=3)
def project_dua_preview(request, project_slug, **kwargs):
    """
    View a project's dua
    """
    project = kwargs['project']

    return render(request, 'project/project_dua_preview.html', {'project': project, 'dua': project.dua})


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
                comments = author_comments_form.cleaned_data['author_comments']
                project.submit(author_comments=comments)
                notification.submit_notify(project)
                messages.success(request, 'Your project has been submitted. You will be notified when an editor is assigned.')
            elif project.integrity_errors:
                messages.error(request, project.integrity_errors)
            else:
                messages.error(request, 'Fix the errors before submitting')
        elif 'resubmit_project' in request.POST and is_submitting:
            author_comments_form = forms.AuthorCommentsForm(data=request.POST)
            if project.is_resubmittable() and author_comments_form.is_valid():
                comments = author_comments_form.cleaned_data['author_comments']
                project.resubmit(author_comments=comments)
                notification.resubmit_notify(project, comments)
                messages.success(request, 'Your project has been resubmitted. You will be notified when the editor makes their decision.')
        # Author approves publication
        elif 'approve_publication' in request.POST:
            author = authors.get(user=user)
            if (request.POST and author.is_submitting and
                request.POST['approve_publication'].isnumeric()):
                try:
                    author = authors.get(id=request.POST['approve_publication'])
                    LOGGER.info('Submitting author {0} for project {1} is approving\
                     on behalf of {2}'.format(user, project, author.user))
                except Author.DoesNotExist:
                    pass
            # Register the approval if valid
            if project.approve_author(author):
                if project.submission_status == SubmissionStatus.NEEDS_PUBLICATION:
                    messages.success(request, 'You have approved the project for publication. The editor will publish it shortly')
                    notification.authors_approved_notify(request, project)
                else:
                    messages.success(request, 'You have approved the project for publication.')
                authors = project.authors.all().order_by('display_order')
            else:
                messages.error(request, 'Invalid')

    # Whether the submission is currently waiting for the user to approve
    awaiting_user_approval = False
    if project.under_submission():
        edit_logs = project.edit_log_history()
        copyedit_logs = project.copyedit_log_history()
        for e in edit_logs:
            e.set_quality_assurance_results()
        # Awaiting authors
        if project.submission_status == SubmissionStatus.NEEDS_APPROVAL:
            authors = authors.order_by('approval_datetime')
            for a in authors:
                a.set_display_info()
                if user == a.user and not a.approval_datetime:
                    awaiting_user_approval = True
    else:
        edit_logs, copyedit_logs = None, None

    if settings.PROJECT_EDITOR_EMAIL:
        contact_email = settings.PROJECT_EDITOR_EMAIL.replace('PROJECT-SLUG',
                                                              project.slug)
    else:
        contact_email = project.editor.email

    return render(
        request,
        "project/project_submission.html",
        {
            "project": project,
            "authors": authors,
            "is_submitting": is_submitting,
            "author_comments_form": author_comments_form,
            "edit_logs": edit_logs,
            "copyedit_logs": copyedit_logs,
            "awaiting_user_approval": awaiting_user_approval,
            "contact_email": contact_email,
        },
    )


@project_auth(auth_mode=0, post_auth_mode=2)
def project_ethics(request, project_slug, **kwargs):
    project = kwargs['project']
    is_submitting = kwargs['is_submitting']

    editable = is_submitting and project.author_editable()

    UploadedDocumentFormSet = generic_inlineformset_factory(
        UploadedDocument,
        fields=(
            'document_type',
            'document',
        ),
        extra=0,
        form=forms.UploadedDocumentForm,
        max_num=forms.UploadedDocumentFormSet.max_forms,
        can_delete=False,
        formset=forms.UploadedDocumentFormSet,
        validate_max=True,
    )

    if request.method == 'POST':
        ethics_form = forms.EthicsForm(data=request.POST, instance=project, editable=editable)
        documents_formset = UploadedDocumentFormSet(data=request.POST, instance=project, files=request.FILES)
        if ethics_form.is_valid() and documents_formset.is_valid():
            project = ethics_form.save()
            documents_formset.save()
            messages.success(request, 'Your project ethics has been updated.')
            documents_formset = UploadedDocumentFormSet(instance=project)
        else:
            messages.error(request, 'Invalid submission. See errors below.')
    else:
        ethics_form = forms.EthicsForm(instance=project, editable=editable)
        documents_formset = UploadedDocumentFormSet(instance=project)

    edit_url = reverse('edit_ethics', kwargs={'project_slug': project.slug})

    return render(
        request,
        'project/project_ethics.html',
        {
            'project': project,
            'ethics_form': ethics_form,
            'is_submitting': kwargs['is_submitting'],
            'documents_formset': documents_formset,
            'add_item_url': edit_url,
            'remove_item_url': edit_url,
        },
    )


@project_auth(auth_mode=0, post_auth_mode=2)
def edit_ethics(request, project_slug, **kwargs):
    project = kwargs['project']

    if project.submission_status not in [SubmissionStatus.UNSUBMITTED, SubmissionStatus.NEEDS_RESUBMISSION]:
        raise Http404()

    # Reload the formset with the first empty form
    if request.method == 'GET' and 'add_first' in request.GET:
        extra_forms = 1
    # Remove an object
    elif request.method == 'POST' and 'remove_id' in request.POST:
        extra_forms = 0
        UploadedDocument.objects.get(id=int(request.POST['remove_id'])).delete()

    UploadedSupportingDocumentFormSet = generic_inlineformset_factory(
        UploadedDocument,
        extra=extra_forms,
        max_num=forms.UploadedDocumentFormSet.max_forms,
        can_delete=False,
        form=forms.UploadedDocumentForm,
        formset=forms.UploadedDocumentFormSet,
        validate_max=True,
    )
    formset = UploadedSupportingDocumentFormSet(instance=project)
    edit_url = reverse('edit_ethics', kwargs={'project_slug': project.slug})

    return render(
        request,
        'project/item_list.html',
        {
            'formset': formset,
            'item': 'affiliation',
            'item_label': formset.item_label,
            'form_name': formset.form_name,
            'add_item_url': edit_url,
            'remove_item_url': edit_url,
        },
    )


@login_required
def serve_document(request, file_name):
    projects = ActiveProject.objects.filter(Q(authors__user=request.user) | Q(editor=request.user)).values_list(
        'id', flat=True
    )
    uploaded_document = get_object_or_404(
        UploadedDocument.objects.filter(
            object_id__in=projects, content_type=ContentType.objects.get_for_model(ActiveProject)
        ),
        document__iendswith=file_name,
    )
    return ProjectFiles().serve_file_field(uploaded_document.document)


@login_required
def archived_submission_history(request, project_slug):
    """
    Submission history for an archived (rejected or closed) project
    """
    user = request.user
    try:
        # Checks if the user is an author
        project = ActiveProject.objects.get(slug=project_slug,
                                            submission_status=SubmissionStatus.ARCHIVED,
                                            authors__user=user)
    except ActiveProject.DoesNotExist:
        if user.has_perm('project.change_activeproject'):
            project = get_object_or_404(ActiveProject,
                                        slug=project_slug,
                                        submission_status=SubmissionStatus.ARCHIVED)
        else:
            raise Http404()

    edit_logs = project.edit_log_history()
    for e in edit_logs:
        e.set_quality_assurance_results()
    copyedit_logs = project.copyedit_log_history()

    return render(request, 'project/archived_submission_history.html',
                  {'project': project, 'edit_logs': edit_logs,
                   'copyedit_logs': copyedit_logs})


def published_versions(request, project_slug):
    """
    List of published versions of a project. Viewable by admins and
    authors.
    """
    user = request.user
    # Account for different authors between versions
    if user.has_perm('project.change_publishedproject'):
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


@login_required
def published_submission_history(request, project_slug, version):
    """
    Submission history for a published project
    """
    user = request.user
    try:
        project = PublishedProject.objects.get(slug=project_slug,
                                               version=version,
                                               authors__user=user)
    except PublishedProject.DoesNotExist:
        if user.has_perm('project.change_publishedproject'):
            project = get_object_or_404(PublishedProject, slug=project_slug,
                                        version=version)
        else:
            raise Http404()

    edit_logs = project.edit_log_history()
    for e in edit_logs:
        e.set_quality_assurance_results()
    copyedit_logs = project.copyedit_log_history()

    return render(request, 'project/published_submission_history.html',
                  {'project': project, 'edit_logs': edit_logs,
                   'copyedit_logs': copyedit_logs, 'published': True})


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

    user = request.user

    # Anonymous access authentication
    an_url = request.get_signed_cookie('anonymousaccess', None, max_age=60*60)
    has_passphrase = project.get_anonymous_url() == an_url

    if can_view_project_files(project, user) or has_passphrase:
        (display_files, display_dirs, dir_breadcrumbs, parent_dir,
         file_error) = get_project_file_info(project=project, subdir=subdir)

        files_panel_url = reverse('published_files_panel',
            args=(project.slug, project.version))

        if request.GET.get('v', '1') == '1':
            template = 'project/files_panel.html'
        else:
            template = 'project/files_panel_v2.html'

        return render(request, template,
            {'project':project, 'subdir':subdir,
             'dir_breadcrumbs':dir_breadcrumbs, 'parent_dir':parent_dir,
             'display_files':display_files, 'display_dirs':display_dirs,
             'files_panel_url':files_panel_url, 'file_error':file_error})
    else:
        raise Http404()

def serve_active_project_file_editor(request, project_slug, full_file_name):
    """
    Serve a file or subdirectory of a published project.
    Works for open and protected. Not needed for open.

    """
    utility.check_http_auth(request)
    try:
        project = ActiveProject.objects.get(slug=project_slug)
    except ObjectDoesNotExist:
        raise Http404()

    user = request.user

    if user.is_authenticated and (project.authors.filter(user=user) or
                                  user == project.editor or user.has_perm('project.change_activeproject')):
        file_path = os.path.join(project.file_root(), full_file_name)
        try:
            attach = ('download' in request.GET)
            return serve_file(file_path, attach=attach, allow_directory=True)
        except IsADirectoryError:
            return redirect(request.path + '/')
        except (NotADirectoryError, FileNotFoundError):
            raise Http404()

    return utility.require_http_auth(request)

def serve_published_project_file(request, project_slug, version,
        full_file_name):
    """
    Serve a file or subdirectory of a published project.
    Works for open and protected. Not needed for open.

    """
    utility.check_http_auth(request)
    try:
        project = PublishedProject.objects.get(slug=project_slug,
            version=version)
    except ObjectDoesNotExist:
        raise Http404()

    user = request.user

    # Anonymous access authentication
    an_url = request.get_signed_cookie('anonymousaccess', None, max_age=60*60)
    has_passphrase = project.get_anonymous_url() == an_url

    if can_view_project_files(project, user) or has_passphrase:
        file_path = os.path.join(project.file_root(), full_file_name)
        try:
            attach = ('download' in request.GET)

            # Temporary workaround: Chromium doesn't permit viewing
            # PDF files in sandboxed mode:
            # https://bugs.chromium.org/p/chromium/issues/detail?id=271452
            # Until this is fixed, disable CSP sandbox for published
            # PDF files.
            if file_path.endswith('.pdf'):
                sandbox = False
            else:
                sandbox = True

            return serve_file(file_path, attach=attach, allow_directory=True,
                              sandbox=sandbox)
        except IsADirectoryError:
            return redirect(request.path + '/')
        except (NotADirectoryError, FileNotFoundError):
            raise Http404()

    return utility.require_http_auth(request)


def display_published_project_file(request, project_slug, version,
                                   full_file_name):
    """
    Display a file in a published project. full_file_name is the file
    path relative to the project's file root.
    """
    try:
        project = PublishedProject.objects.get(slug=project_slug,
                                               version=version)
    except ObjectDoesNotExist:
        raise Http404()

    user = request.user

    # Anonymous access authentication
    an_url = request.get_signed_cookie('anonymousaccess', None, max_age=60*60)
    has_passphrase = project.get_anonymous_url() == an_url

    if can_view_project_files(project, user) or has_passphrase:
        return display_project_file(request, project, full_file_name)

    # Display error message: "you must [be a credentialed user and]
    # sign the data use agreement"
    breadcrumbs = utility.get_dir_breadcrumbs(full_file_name, directory=False)
    context = {
        'project': project,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'project/file_view_unauthorized.html',
                  context, status=403)


def serve_published_project_zip(request, project_slug, version):
    """
    Serve the zip file of a published project.
    Works for open and protected. Not needed for open.

    """
    utility.check_http_auth(request)
    try:
        project = PublishedProject.objects.get(slug=project_slug,
            version=version)
    except ObjectDoesNotExist:
        raise Http404()

    user = request.user

    # Anonymous access authentication
    an_url = request.get_signed_cookie('anonymousaccess', None, max_age=60*60)
    has_passphrase = project.get_anonymous_url() == an_url

    if can_view_project_files(project, user) or has_passphrase:
        try:
            return serve_file(project.zip_name(full=True))
        except FileNotFoundError:
            raise Http404()

    return utility.require_http_auth(request)


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


def published_project_required_training(request, project_slug, version):
    """Displays a published project's required training"""
    project = get_object_or_404(PublishedProject, slug=project_slug, version=version)

    required_trainings = project.required_trainings.all()

    return render(
        request,
        'project/published_project_required_training.html',
        {'project': project, 'required_training': required_trainings},
    )


def published_project_dua(request, project_slug, version):
    """Displays a published project's dua"""
    project = get_object_or_404(PublishedProject, slug=project_slug, version=version)

    return render(
        request,
        'project/published_project_dua.html', {'project': project},
    )



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
    references = project.references.all().order_by('order')
    publication = project.publications.all().first()
    topics = project.topics.all()
    languages = project.programming_languages.all()
    contact = project.contact
    news = project.news.all().order_by('-publish_datetime')
    parent_projects = project.parent_projects.all()
    # derived_projects = project.derived_publishedprojects.all()
    data_access = DataAccess.objects.filter(project=project)
    user = request.user
    _, _, _, _, _, latest_version = project.info_card()
    citations = project.citation_text_all()
    platform_citations = project.get_platform_citation()
    show_platform_wide_citation = any(platform_citations.values())
    main_platform_citation = next((item for item in platform_citations.values() if item is not None), '')

    # Anonymous access authentication
    an_url = request.get_signed_cookie('anonymousaccess', None, max_age=60 * 60)
    has_passphrase = project.get_anonymous_url() == an_url

    can_view_files = can_view_project_files(project, user) or has_passphrase
    is_authorized = can_access_project(project, user) or has_passphrase
    has_signed_dua = False if not user.is_authenticated else DUASignature.objects.filter(
        project=project,
        user=user
    ).exists()
    has_accepted_access_request = False if not user.is_authenticated else DataAccessRequest.objects.get_active(
        project=project,
        requester=user,
        status=DataAccessRequest.ACCEPT_REQUEST_VALUE
    ).exists()

    if project.required_trainings.exists():
        requires_training = True
    else:
        requires_training = False

    has_required_training = (
        False
        if not user.is_authenticated
        else Training.objects.get_valid().filter(training_type__in=project.required_trainings.all(), user=user).count()
        == project.required_trainings.count()
    )
    current_site = get_current_site(request)
    bulk_url_prefix = notification.get_url_prefix(request, bulk_download=True)
    all_project_versions = PublishedProject.objects.filter(slug=project_slug).order_by('version_order')
    context = {
        'project': project,
        'authors': authors,
        'references': references,
        'publication': publication,
        'topics': topics,
        'languages': languages,
        'contact': contact,
        'is_authorized': is_authorized,
        'can_view_files': can_view_files,
        'has_signed_dua': has_signed_dua,
        'has_accepted_access_request': has_accepted_access_request,
        'requires_training': requires_training,
        'has_required_training': has_required_training,
        'current_site': current_site,
        'bulk_url_prefix': bulk_url_prefix,
        'latest_version': latest_version,
        'citations': citations,
        'news': news,
        'all_project_versions': all_project_versions,
        'parent_projects': parent_projects,
        'data_access': data_access,
        'messages': messages.get_messages(request),
        'platform_citations': platform_citations,
        'is_lightwave_supported': project.files.is_lightwave_supported(),
        'is_wget_supported': project.files.is_wget_supported(),
        'has_s3_credentials': has_s3_credentials(),
        'show_platform_wide_citation': show_platform_wide_citation,
        'main_platform_citation': main_platform_citation,
    }
    # The file and directory contents
    if can_view_files:
        if user.is_authenticated:
            AccessLog.objects.update_or_create(project=project, user=request.user)

        (display_files, display_dirs, dir_breadcrumbs, parent_dir,
         file_error) = get_project_file_info(project=project, subdir=subdir)
        if file_error:
            status = 404
        else:
            status = 200

        main_size, compressed_size = [
            utility.readable_size(s) for s in (project.main_storage_size, project.compressed_storage_size)
        ]
        files_panel_url = reverse('published_files_panel', args=(project.slug, project.version))
        accepted_access_request = [] if not user.is_authenticated else (
            DataAccessRequest.objects.get_active(
                project=project, requester=user, status=DataAccessRequest.ACCEPT_REQUEST_VALUE
            )
        )
        context = {
            **context,
            **{
                'dir_breadcrumbs': dir_breadcrumbs,
                'main_size': main_size,
                'compressed_size': compressed_size,
                'display_files': display_files,
                'display_dirs': display_dirs,
                'files_panel_url': files_panel_url,
                'subdir': subdir,
                'parent_dir': parent_dir,
                'file_error': file_error,
                'current_site': get_current_site(request),
                'data_access': data_access,
                'accepted_access_requests': accepted_access_request,
            },
        }
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
    from console.views import update_aws_bucket_policy
    user = request.user
    project = PublishedProject.objects.filter(slug=project_slug, version=version)
    if project:
        project = project.get()
    else:
        raise Http404()

    if (
        project.deprecated_files
        or project.embargo_active()
        or project.access_policy not in {AccessPolicy.RESTRICTED, AccessPolicy.CREDENTIALED}
        or can_access_project(project, user)
    ):
        return redirect('published_project',
                        project_slug=project_slug, version=version)

    if project.access_policy == AccessPolicy.CREDENTIALED and not user.is_credentialed:
        return render(request, 'project/credential_required.html')

    license = project.license
    license_content = project.license_content(fmt='html')

    if request.method == 'POST' and 'agree' in request.POST:
        DUASignature.objects.create(user=user, project=project)
        if has_s3_credentials() and files_sent_to_S3(project) is not None:
            update_aws_bucket_policy(project.id)
        return render(request, 'project/sign_dua_complete.html', {
            'project':project})

    return render(request, 'project/sign_dua.html', {'project':project,
        'license':license, 'license_content':license_content})


@login_required
def request_data_access(request, project_slug, version):
    """
    Form for a user (requester) to request access to the data of a self managed project.
    """
    project = get_object_or_404(PublishedProject, slug=project_slug, version=version)

    if project.access_policy != AccessPolicy.CONTRIBUTOR_REVIEW:
        return redirect('published_project', project_slug=project_slug, version=version)

    if request.method == 'POST':
        access_request_form = forms.DataAccessRequestForm(
            project=project, requester=request.user, template=None, prefix="proj", data=request.POST
        )

        if access_request_form.is_valid():
            access_request = access_request_form.save()

            corresponding_author = project.corresponding_author().user
            reviewers = [reviewer.reviewer for reviewer in DataAccessRequestReviewer.objects.filter(
                project=project, reviewer=request.user, is_revoked=False
            )]

            notification.notify_owner_data_access_request(
                reviewers + [corresponding_author], access_request, request.scheme, request.get_host()
            )
            notification.confirm_user_data_access_request(access_request, request.scheme, request.get_host())

            response = render(request, 'project/data_access_request_submitted.html', {'project': project})
            set_saved_fields_cookie(access_request_form, request.path, response)

            return response
    else:
        project_request_form = forms.DataAccessRequestForm(
            project=project, requester=request.user, template=project.dua.access_template, prefix="proj"
        )

    accepted_requests = DataAccessRequest.objects.filter(
        requester=request.user, project=project, status=DataAccessRequest.ACCEPT_REQUEST_VALUE
    ).exists()

    needs_credentialing = project.access_policy == AccessPolicy.CREDENTIALED and not request.user.is_credentialed

    full_user_name = request.user.get_full_name()

    return render(request, 'project/request_data_access.html',
                  {'project_request_form': project_request_form,
                   'needs_credentialing': needs_credentialing,
                   'full_user_name': full_user_name,
                   'project': project,
                   'accepted_requests': accepted_requests,
                   })


@login_required
def data_access_request_status(request, project_slug, version):
    """
    Requester can view the state of his/her data access request for a self managed
    project
    """
    project = get_object_or_404(PublishedProject, slug=project_slug, version=version)

    if project.access_policy != AccessPolicy.CONTRIBUTOR_REVIEW:
        return redirect('published_project', project_slug=project_slug, version=version)

    access_requests = DataAccessRequest.objects.filter(
        requester=request.user, project=project
    ).order_by('-request_datetime')

    if not access_requests.exists():
        return redirect('request_data_access', project_slug=project.slug, version=project.version)

    if request.method == 'POST' and 'withdraw_request_id' in request.POST.keys():
        access_request = get_object_or_404(
            DataAccessRequest, requester=request.user, project=project, id=request.POST['withdraw_request_id']
        )
        access_request.status = DataAccessRequest.WITHDRAWN_VALUE
        access_request.decision_datetime = timezone.now()
        access_request.save()

    return render(request, 'project/data_access_request_status.html', {
        'access_requests': access_requests,
        'project': project,
        'max_review_days': DataAccessRequest.DATA_ACCESS_REQUESTS_DAY_LIMIT
    })


@login_required
def data_access_request_status_detail(request, project_slug, version, pk):
    project = get_object_or_404(PublishedProject, slug=project_slug, version=version)
    access_request = get_object_or_404(
        DataAccessRequest, requester=request.user, project=project, pk=pk
    )

    return render(request, 'project/data_access_request_status_detail.html', {
        'access_request': access_request,
        'project': project,
    })


@login_required
def data_access_requests_overview(request, project_slug, version):
    """
    Overview over all issued access requests for the request reviewer(s)
    """
    reviewer = request.user

    try:
        proj = PublishedProject.objects.get(slug=project_slug, version=version)
    except PublishedProject.DoesNotExist:
        raise Http404(Exception("The project doesn't exist"))

    if proj.access_policy != AccessPolicy.CONTRIBUTOR_REVIEW:
        return redirect('published_project',
                        project_slug=project_slug, version=version)

    if not proj.can_approve_requests(reviewer):
        raise Http404("You don't have access to the project requests overview.")

    if request.method == 'POST':
        if 'stop_review' in request.POST.keys():
            try:
                entry = DataAccessRequestReviewer.objects.get(
                    project=proj, reviewer_id=reviewer.id, is_revoked=False)
                entry.revoke()

                notification.notify_owner_data_access_review_withdrawal(entry)
                return redirect('project_home')
            except DataAccessRequestReviewer.DoesNotExist:
                pass
        elif 'revoke_request_id' in request.POST.keys():
            access_request = get_object_or_404(DataAccessRequest, pk=request.POST['revoke_request_id'])
            access_request.status = DataAccessRequest.REVOKED_VALUE
            access_request.save()

    all_requests = DataAccessRequest.objects.filter(project_id=proj).order_by(
        '-request_datetime')

    accepted_requests = all_requests.filter(
        status=DataAccessRequest.ACCEPT_REQUEST_VALUE).count()

    return render(request, 'project/data_access_requests_overview.html',
                  {'project': proj,
                   'requests': all_requests,
                   'accepted_requests': accepted_requests,
                   'is_additional_reviewer': proj.is_data_access_reviewer(reviewer)})


@login_required
def data_access_request_view(request, project_slug, version, pk):
    """
    Responder/reviewer can see the data associated with a specific access request
    to his/her project
    """
    project = get_object_or_404(PublishedProject, slug=project_slug, version=version)
    access_request = get_object_or_404(DataAccessRequest, pk=pk, project=project)

    if project.access_policy != AccessPolicy.CONTRIBUTOR_REVIEW:
        return redirect('published_project', project_slug=project_slug, version=version)

    if not project.can_approve_requests(request.user):
        raise Http404("You don't have access to the project requests overview")

    if request.method == 'POST':
        response_form = forms.DataAccessResponseForm(
            responder=request.user, prefix="proj", data=request.POST, instance=access_request
        )

        if response_form.is_valid():
            response_form.save()
            notification.notify_user_data_access_request(access_request, request.scheme, request.get_host())
            return redirect('data_access_requests_overview', project_slug=project_slug, version=version)

        access_request.refresh_from_db()
    else:
        response_form = forms.DataAccessResponseForm(responder=request.user, prefix="proj")

    credentialing_data = CredentialApplication.objects.filter(
        user=request.user
    ).order_by("-application_datetime").first()

    legacy_credentialing_data = None
    if credentialing_data is None:
        try:
            legacy_credentialing_data = LegacyCredential.objects.filter(
                migrated_user_id=access_request.requester
            ).order_by("-mimic_approval_date").first()
        except LegacyCredential.DoesNotExist:
            pass

    other_access_requests = DataAccessRequest.objects.exclude(pk=pk).filter(
        requester=access_request.requester, project=project
    ).order_by('-request_datetime')

    return render(request, 'project/data_access_request_view.html', {
        'access_request': access_request,
        'other_access_requests': other_access_requests,
        'response_form': response_form,
        'credentialing_data': credentialing_data,
        'legacy_credentialing_data': legacy_credentialing_data,
    })

@login_required
def manage_data_access_reviewers(request, project_slug, version):
    """
    Corresponding author of a self managed credentialing project can invite additional
    users to help review incoming data access requests.
    The invitation can also be revoked
    """

    try:
        project = PublishedProject.objects.get(slug=project_slug, version=version)
    except:
        raise Http404(Exception("The project doesn't exist"))

    if project.access_policy != AccessPolicy.CONTRIBUTOR_REVIEW:
        return redirect('project_home')

    reviewer_manager = request.user

    if not project.can_manage_data_access_reviewers(reviewer_manager):
        raise Http404(
            Exception("You don't have access to this view"))

    form = forms.InviteDataAccessReviewerForm(project=project)
    if request.method == 'POST' and 'invite_reviewer' in request.POST.keys():
        form = forms.InviteDataAccessReviewerForm(data=request.POST, project=project)

        if form.is_valid():
            invitation = form.save()
            notification.notify_user_invited_managing_requests(invitation,
                                                               request.scheme,
                                                               request.get_host())
    elif request.method == 'POST' and 'revoke_reviewer' in request.POST.keys():
        reviewer_id = request.POST['revoke_reviewer']

        try:
            entry = DataAccessRequestReviewer.objects.get(
                project=project, reviewer_id=reviewer_id, is_revoked=False)
            entry.revoke()
        except DataAccessRequestReviewer.DoesNotExist:
            pass

    reviewers_list = DataAccessRequestReviewer.objects.filter(
        project=project).order_by("is_revoked", "-revocation_date",
                                  "reviewer__profile__first_names")

    return render(request, 'project/manage_data_access_reviewers.html',
                  {'project': project,
                   'invite_reviewer_form': form,
                   'reviewers_list': reviewers_list})


@login_required
def published_project_request_access(request, project_slug, version, access_type):
    """
    Page to grant access to AWS storage, Google storage or Big Query
    to a specific user.
    """
    user = request.user
    project = PublishedProject.objects.get(slug=project_slug, version=version)
    data_access = DataAccess.objects.filter(project=project,
                                            platform=access_type)

    # Check if the person has access to the project.
    if not can_access_project(project, user):
        return redirect('published_project', project_slug=project_slug,
            version=version)

    try:
        # check user if user has GCP or AWS info in profile
        if (user.cloud_information.gcp_email is None and access_type in [3, 4]) or (
            user.cloud_information.aws_id is None and access_type == 2):
            messages.error(request, 'Please set the user cloud information in your settings')
            return redirect('edit_cloud')
    except CloudInformation.DoesNotExist:
        messages.error(request, 'Please set the user cloud information in your settings')
        return redirect('edit_cloud')

    for access in data_access:
        if access_type == 2 and access.platform == access_type:
            message, granted_access = utility.grant_aws_open_data_access(user, project)
            notification.notify_aws_access_request(user, project, access, granted_access)
            if granted_access:
                messages.success(request, message)
            else:
                messages.error(request, message)
        elif access_type in [3, 4] and access.platform == access_type:
            message, granted_access = utility.grant_gcp_group_access(user, project, access)
            notification.notify_gcp_access_request(access, user, project, granted_access)
            if granted_access:
                messages.success(request, message)
            else:
                messages.error(request, message)

    return redirect('published_project', project_slug=project_slug, version=version)


def anonymous_login(request, anonymous_url):
    # Validate project url
    try:
        project = AnonymousAccess.objects.get(url=anonymous_url).project

        if project.__class__ == PublishedProject:
            response = redirect('published_project', project_slug=project.slug, version=project.version)
        else:
            response = redirect('project_preview', project_slug=project.slug)

    except ObjectDoesNotExist:
        raise Http404()

    # Empty form
    form = forms.AnonymousAccessLoginForm()

    # Validate input from submission
    if request.method == 'POST':
        form = forms.AnonymousAccessLoginForm(data=request.POST)
        if form.is_valid():
            # Validates passphrase
            passphrase = request.POST["passphrase"]
            if project.is_valid_passphrase(passphrase):
                # Set cookie and redirects to project page
                response.set_signed_cookie('anonymousaccess', anonymous_url,
                                           max_age=60*60, httponly=True,
                                           secure=(not settings.DEBUG),
                                           samesite='Lax')
                return response

            # Did not find any valid passphrase
            messages.error(request, 'Invalid passphrase.')
        else:
            # Invalid form error
            messages.error(request, 'Submission unsuccessful. See form for errors.')

    return render(request, 'project/anonymous_login.html', {'anonymous_url': anonymous_url,
                  'form': form})


@login_required
def generate_signed_url(request, project_slug):
    """
    API endpoint to generate a signed URL to access project files on GCS.
    """
    filename = request.POST.get('filename')
    size = request.POST.get('size')

    try:
        validate_gcs_bucket_object(filename, size)
    except ValidationError as e:
        return JsonResponse({'detail': e.messages}, status=400)

    size = int(size)
    queryset = ActiveProject.objects.all()
    project = get_object_or_404(queryset, slug=project_slug)

    if not project.is_editable_by(request.user):
        return JsonResponse({'detail': 'User is not authorized to edit the project at this moment.'}, status=403)

    if size > project.get_storage_info().remaining:
        return JsonResponse({'detail': 'The file size cannot be greater than the remaining space.'}, status=400)

    canonical_resource = f'active-projects/{project_slug}/{filename.strip("/")}'

    url = generate_signed_url_helper(
        version='v4',
        blob_name=canonical_resource,
        expiration=dt.timedelta(minutes=settings.GCS_SIGNED_URL_LIFETIME_IN_MINUTES),
        size=size
    )

    data = f'filename: {filename};size: {size // (1024)}kB'
    GCPLog.objects.update_or_create(project=project, user=request.user, data=data)

    return JsonResponse({'url': url})
