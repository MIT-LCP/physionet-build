import re
import pdb
import logging
import os
import csv
from datetime import datetime, timedelta
from itertools import chain
from statistics import median, StatisticsError
from collections import OrderedDict

from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import validate_email
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.db import DatabaseError, transaction
from django.db.models import (Q, CharField, Value, IntegerField, F, functions,
    DurationField)
from django.db.models.functions import Cast
from background_task import background
from django.contrib.sites.models import Site
from dal import autocomplete

from notification.models import News
import notification.utility as notification
from physionet.middleware.maintenance import ServiceUnavailable
from physionet.utility import paginate
import project.forms as project_forms
from project.models import (ActiveProject, ArchivedProject, StorageRequest,
    Reference, Topic, Publication, PublishedProject,
    exists_project_slug, GCP, DUASignature, DataAccess)
from project.utility import readable_size
from project.validators import MAX_PROJECT_SLUG_LENGTH
from project.views import (get_file_forms, get_project_file_info,
    process_files_post)
from user.models import (User, CredentialApplication, LegacyCredential,
                         AssociatedEmail, CredentialReview)
from console import forms, utility
from console.tasks import associated_task, get_associated_tasks

from django.conf import settings

LOGGER = logging.getLogger(__name__)


@associated_task(PublishedProject, 'pid')
@background()
def make_zip_background(pid):
    """
    Schedule a background task to make the zip file
    """
    project = PublishedProject.objects.get(id=pid)
    # Create zip file if there are files. Should always be the case.
    project.make_zip()
    project.set_storage_info()


@associated_task(PublishedProject, 'pid')
@background()
def make_checksum_background(pid):
    """
    Schedule a background task to make the checksum file
    """
    project = PublishedProject.objects.get(id=pid)
    # Create checksum file if there are files. Should always be the case.
    project.make_checksum_file()
    project.set_storage_info()


def is_admin(user, *args, **kwargs):
    return user.is_admin


def handling_editor(base_view):
    """
    Access decorator. The user must be the editor of the project.
    """
    @login_required
    def handling_view(request, *args, **kwargs):
        user = request.user
        try:
            project = ActiveProject.objects.get(slug=kwargs['project_slug'])
            if user.is_admin and user == project.editor:
                kwargs['project'] = project
                return base_view(request, *args, **kwargs)
        except ActiveProject.DoesNotExist:
            raise Http404()
        raise Http404('Unable to access page')
    return handling_view

# ------------------------- Views begin ------------------------- #


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def console_home(request):
    return redirect('submitted_projects')


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def submitted_projects(request):
    """
    List of active submissions. Editors are assigned here.
    """
    user = request.user
    if request.method == 'POST':
        assign_editor_form = forms.AssignEditorForm(request.POST)
        if assign_editor_form.is_valid():
            # Move this into project method
            project = ActiveProject.objects.get(id=assign_editor_form.cleaned_data['project'])
            project.assign_editor(assign_editor_form.cleaned_data['editor'])
            notification.assign_editor_notify(project)
            notification.editor_notify_new_project(project, user)
            messages.success(request, 'The editor has been assigned')

    # Submitted projects
    projects = ActiveProject.objects.filter(submission_status__gt=0).order_by(
        'submission_datetime')
    # Separate projects by submission status
    # Awaiting editor assignment
    assignment_projects = projects.filter(submission_status=10)
    # Awaiting editor decision
    decision_projects = projects.filter(submission_status=20)
    # Awaiting author revisions
    revision_projects = projects.filter(submission_status=30)
    # Awaiting editor copyedit
    copyedit_projects = projects.filter(submission_status=40)
    # Awaiting author approval
    approval_projects = projects.filter(submission_status=50)
    # Awaiting editor publish
    publish_projects = projects.filter(submission_status=60)

    assign_editor_form = forms.AssignEditorForm()

    # Time to check if the reminder email can be sent
    yesterday = timezone.now() + timezone.timedelta(days=-1)

    if request.method == "POST":
        try:
            if 'send_approval_reminder' in request.POST:
                pid = request.POST.get('send_approval_reminder', '')
                project = ActiveProject.objects.get(id=pid)
                notification.copyedit_complete_notify(request, project,
                    project.copyedit_logs.last(), reminder=True)
                project.latest_reminder = timezone.now()
                project.save()
                messages.success(request, 'The reminder email has been sent.')
            elif 'send_revision_reminder' in request.POST:
                pid = request.POST.get('send_revision_reminder', '')
                project = ActiveProject.objects.get(id=pid)
                notification.edit_decision_notify(request, project,
                    project.edit_logs.last(), reminder=True)
                project.latest_reminder = timezone.now()
                project.save()
                messages.success(request, 'The reminder email has been sent.')
        except (ValueError, ActiveProject.DoesNotExist):
            pass
    return render(request, 'console/submitted_projects.html',
        {'assign_editor_form': assign_editor_form,
         'assignment_projects': assignment_projects,
         'decision_projects': decision_projects,
         'revision_projects': revision_projects,
         'copyedit_projects': copyedit_projects,
         'approval_projects': approval_projects,
         'publish_projects': publish_projects,
         'submitted_projects_nav': True,
         'yesterday': yesterday})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def editor_home(request):
    """
    List of submissions the editor is responsible for
    """
    projects = ActiveProject.objects.filter(editor=request.user).order_by(
        'submission_datetime')

    # Awaiting editor decision
    decision_projects = projects.filter(submission_status=20)
    # Awaiting author revisions
    revision_projects = projects.filter(submission_status=30)
    # Awaiting editor copyedit
    copyedit_projects = projects.filter(submission_status=40)
    # Awaiting author approval
    approval_projects = projects.filter(submission_status=50)
    # Awaiting editor publish
    publish_projects = projects.filter(submission_status=60)

    # Time to check if the reminder email can be sent
    yesterday = timezone.now() + timezone.timedelta(days=-1)

    if request.method == "POST" and 'send_reminder' in request.POST:
        try:
            pid = request.POST.get('send_reminder', '')
            project = ActiveProject.objects.get(id=pid)
            notification.edit_decision_notify(request, project,
                project.edit_logs.last(), reminder=True)
            project.latest_reminder = timezone.now()
            project.save()
            messages.success(request, 'The reminder email has been sent.')
        except (ValueError, ActiveProject.DoesNotExist):
            pass
    return render(request, 'console/editor_home.html',
        {'decision_projects': decision_projects,
         'revision_projects': revision_projects,
         'copyedit_projects': copyedit_projects,
         'approval_projects': approval_projects,
         'publish_projects': publish_projects,
         'yesterday': yesterday, 'editor_home': True})


def submission_info_redirect(request, project_slug):
    return redirect('submission_info', project_slug=project_slug)


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def submission_info(request, project_slug):
    """
    View information about a project under submission
    """
    try:
        project = ActiveProject.objects.get(slug=project_slug)
    except ActiveProject.DoesNotExist:
        raise Http404()

    user = request.user
    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()

    data = request.POST or None
    reassign_editor_form = forms.ReassignEditorForm(user, data=data)
    passphrase = ''
    anonymous_url = project.get_anonymous_url()

    if 'generate_passphrase' in request.POST:
        anonymous_url, passphrase = project.generate_anonymous_access()
    elif 'remove_passphrase' in request.POST:
        project.anonymous.all().delete()
        anonymous_url, passphrase = '', 'revoked'
    elif 'reassign_editor' in request.POST and reassign_editor_form.is_valid():
        project.reassign_editor(reassign_editor_form.cleaned_data['editor'])
        notification.editor_notify_new_project(project, user, reassigned=True)
        messages.success(request, 'The editor has been reassigned')
        LOGGER.info("The editor for the project {0} has been reassigned from "
                    "{1} to {2}".format(project, user,
                        reassign_editor_form.cleaned_data['editor']))

    url_prefix = notification.get_url_prefix(request)
    return render(request, 'console/submission_info.html',
        {'project': project, 'authors': authors,
         'author_emails': author_emails, 'storage_info': storage_info,
         'edit_logs': edit_logs, 'copyedit_logs': copyedit_logs,
         'latest_version': latest_version, 'passphrase': passphrase,
         'anonymous_url': anonymous_url, 'url_prefix': url_prefix,
         'reassign_editor_form': reassign_editor_form,
         'project_info_nav': True})


@handling_editor
def edit_submission(request, project_slug, *args, **kwargs):
    """
    Page to respond to a particular submission, as an editor
    """
    project = kwargs['project']
    edit_log = project.edit_logs.get(decision_datetime__isnull=True)
    reassign_editor_form = forms.ReassignEditorForm(request.user)

    # The user must be the editor
    if project.submission_status not in [20, 30]:
        return redirect('editor_home')

    if request.method == 'POST':
        edit_submission_form = forms.EditSubmissionForm(
            resource_type=project.resource_type, instance=edit_log,
            data=request.POST)
        if edit_submission_form.is_valid():
            # This processes the resulting decision
            edit_log = edit_submission_form.save()
            # Set the display labels for the quality assurance results
            edit_log.set_quality_assurance_results()
            # The original object will be deleted if the decision is reject
            if edit_log.decision == 0:
                project = ArchivedProject.objects.get(slug=project_slug)
            # Notify the authors
            notification.edit_decision_notify(request, project, edit_log)
            return render(request, 'console/edit_complete.html',
                {'decision': edit_log.decision, 'editor_home': True,
                 'project': project, 'edit_log': edit_log})
        messages.error(request, 'Invalid response. See form below.')
    else:
        edit_submission_form = forms.EditSubmissionForm(
            resource_type=project.resource_type, instance=edit_log)

    authors, author_emails, storage_info, edit_logs, _, latest_version = project.info_card()
    url_prefix = notification.get_url_prefix(request)

    return render(request, 'console/edit_submission.html',
        {'project': project, 'edit_submission_form': edit_submission_form,
         'authors': authors, 'author_emails': author_emails,
         'storage_info': storage_info, 'edit_logs': edit_logs,
         'latest_version': latest_version, 'url_prefix': url_prefix,
         'editor_home': True, 'reassign_editor_form': reassign_editor_form})


@handling_editor
def copyedit_submission(request, project_slug, *args, **kwargs):
    """
    Page to copyedit the submission
    """
    project = kwargs['project']
    if project.submission_status != 40:
        return redirect('editor_home')

    copyedit_log = project.copyedit_logs.get(complete_datetime=None)
    reassign_editor_form = forms.ReassignEditorForm(request.user)

    # Metadata forms and formsets
    ReferenceFormSet = generic_inlineformset_factory(Reference,
        fields=('description',), extra=0,
        max_num=project_forms.ReferenceFormSet.max_forms, can_delete=False,
        formset=project_forms.ReferenceFormSet, validate_max=True)
    TopicFormSet = generic_inlineformset_factory(Topic,
        fields=('description',), extra=0,
        max_num=project_forms.TopicFormSet.max_forms, can_delete=False,
        formset=project_forms.TopicFormSet, validate_max=True)
    PublicationFormSet = generic_inlineformset_factory(Publication,
        fields=('citation', 'url'), extra=0,
        max_num=project_forms.PublicationFormSet.max_forms, can_delete=False,
        formset=project_forms.PublicationFormSet, validate_max=True)

    description_form = project_forms.ContentForm(
        resource_type=project.resource_type.id, instance=project)
    access_form = project_forms.AccessMetadataForm(instance=project)
    discovery_form = project_forms.DiscoveryForm(resource_type=project.resource_type.id,
        instance=project)

    access_form.set_license_queryset(access_policy=project.access_policy)
    reference_formset = ReferenceFormSet(instance=project)
    publication_formset = PublicationFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    copyedit_form = forms.CopyeditForm(instance=copyedit_log)

    if request.method == 'POST':
        if 'edit_content' in request.POST:
            description_form = project_forms.ContentForm(
                resource_type=project.resource_type.id, data=request.POST,
                instance=project)
            access_form = project_forms.AccessMetadataForm(data=request.POST,
                instance=project)
            discovery_form = project_forms.DiscoveryForm(
                resource_type=project.resource_type, data=request.POST,
                instance=project)
            reference_formset = ReferenceFormSet(data=request.POST,
                instance=project)
            publication_formset = PublicationFormSet(request.POST,
                                                 instance=project)
            topic_formset = TopicFormSet(request.POST, instance=project)
            if (description_form.is_valid() and access_form.is_valid()
                                            and reference_formset.is_valid()
                                            and publication_formset.is_valid()
                                            and topic_formset.is_valid()
                                            and discovery_form.is_valid()):
                description_form.save()
                access_form.save()
                discovery_form.save()
                reference_formset.save()
                publication_formset.save()
                topic_formset.save()
                messages.success(request,
                    'The project metadata has been updated.')
                # Reload formsets
                reference_formset = ReferenceFormSet(instance=project)
                publication_formset = PublicationFormSet(instance=project)
                topic_formset = TopicFormSet(instance=project)
            else:
                messages.error(request,
                    'Invalid submission. See errors below.')
            access_form.set_license_queryset(access_policy=access_form.instance.access_policy)
        elif 'complete_copyedit' in request.POST:
            copyedit_form = forms.CopyeditForm(request.POST,
                instance=copyedit_log)
            if copyedit_form.is_valid():
                copyedit_log = copyedit_form.save()
                notification.copyedit_complete_notify(request, project,
                    copyedit_log)
                return render(request, 'console/copyedit_complete.html',
                    {'project': project, 'copyedit_log': copyedit_log,
                     'editor_home': True})
            else:
                messages.error(request, 'Invalid submission. See errors below.')
        else:
            # process the file manipulation post
            subdir = process_files_post(request, project)

    if 'subdir' not in vars():
        subdir = ''

    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()

    (display_files, display_dirs, dir_breadcrumbs, _,
     file_error) = get_project_file_info(project=project, subdir=subdir)

    (upload_files_form, create_folder_form, rename_item_form,
     move_items_form, delete_items_form) = get_file_forms(
         project=project, subdir=subdir, display_dirs=display_dirs)

    edit_url = reverse('edit_content_item', args=[project.slug])
    url_prefix = notification.get_url_prefix(request)

    return render(request, 'console/copyedit_submission.html', {
        'project': project, 'description_form': description_form,
        'individual_size_limit': readable_size(ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT),
        'access_form': access_form, 'reference_formset':reference_formset,
        'publication_formset': publication_formset,
        'topic_formset': topic_formset,
        'storage_info': storage_info, 'upload_files_form':upload_files_form,
        'create_folder_form': create_folder_form,
        'rename_item_form': rename_item_form,
        'move_items_form': move_items_form,
        'delete_items_form': delete_items_form,
        'subdir': subdir, 'display_files': display_files,
        'display_dirs': display_dirs, 'dir_breadcrumbs': dir_breadcrumbs,
        'file_error': file_error, 'editor_home': True,
        'is_editor': True, 'files_editable': True,
        'copyedit_form': copyedit_form,
        'authors': authors, 'author_emails': author_emails,
        'storage_info': storage_info, 'edit_logs': edit_logs,
        'copyedit_logs': copyedit_logs, 'latest_version': latest_version,
        'add_item_url': edit_url, 'remove_item_url': edit_url,
        'discovery_form': discovery_form, 'url_prefix': url_prefix,
        'reassign_editor_form': reassign_editor_form})


@handling_editor
def awaiting_authors(request, project_slug, *args, **kwargs):
    """
    View the authors who have and have not approved the project for
    publication.

    Also the page to reopen the project for copyediting.
    """
    project = kwargs['project']

    if project.submission_status != 50:
        return redirect('editor_home')

    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()
    outstanding_emails = ';'.join([a.user.email for a in authors.filter(
        approval_datetime=None)])
    reassign_editor_form = forms.ReassignEditorForm(request.user)

    if request.method == 'POST':
        if 'reopen_copyedit' in request.POST:
            project.reopen_copyedit()
            notification.reopen_copyedit_notify(request, project)
            return render(request, 'console/reopen_copyedit_complete.html',
                {'project':project})
        elif 'send_reminder' in request.POST:
            notification.copyedit_complete_notify(request, project,
                project.copyedit_logs.last(), reminder=True)
            messages.success(request, 'The reminder email has been sent.')
            project.latest_reminder = timezone.now()
            project.save()

    url_prefix = notification.get_url_prefix(request)
    yesterday = timezone.now() + timezone.timedelta(days=-1)

    return render(request, 'console/awaiting_authors.html',
        {'project': project, 'authors': authors, 'author_emails': author_emails,
         'storage_info': storage_info, 'edit_logs': edit_logs,
         'copyedit_logs': copyedit_logs, 'latest_version': latest_version,
         'outstanding_emails': outstanding_emails, 'url_prefix': url_prefix,
         'yesterday': yesterday, 'editor_home': True,
         'reassign_editor_form': reassign_editor_form})


@handling_editor
def publish_slug_available(request, project_slug, *args, **kwargs):
    """
    Return whether a slug is available to use to publish an active
    project.

    """
    desired_slug = request.GET['desired_slug']
    # Slug belongs to this project
    if project_slug == desired_slug:
        result = True
    # Check if any project has claimed it
    else:
        result = not exists_project_slug(desired_slug)

    return JsonResponse({'available':result})


@handling_editor
def publish_submission(request, project_slug, *args, **kwargs):
    """
    Page to publish the submission
    """
    project = kwargs['project']

    if project.submission_status != 60:
        return redirect('editor_home')
    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        raise ServiceUnavailable()

    reassign_editor_form = forms.ReassignEditorForm(request.user)
    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()
    if request.method == 'POST':
        publish_form = forms.PublishForm(project=project, data=request.POST)
        if project.is_publishable() and publish_form.is_valid():
            if project.version_order:
                slug = project.get_previous_slug()
            else:
                slug = publish_form.cleaned_data['slug']
            published_project = project.publish(slug=slug,
                make_zip=int(publish_form.cleaned_data['make_zip']))
            notification.publish_notify(request, published_project)

            # update the core and project DOIs with latest metadata
            if published_project.core_project.doi:
                core = published_project.core_project
                latest = core.publishedprojects.get(is_latest_version=True)
                payload_core = utility.generate_doi_payload(latest,
                                                            core_project=True,
                                                            event="publish")
                utility.update_doi(core.doi, payload_core)

            if published_project.doi:
                payload = utility.generate_doi_payload(published_project,
                                                       core_project=False,
                                                       event="publish")
                utility.update_doi(published_project.doi, payload)

            return render(request, 'console/publish_complete.html',
                {'published_project': published_project, 'editor_home': True})

    publishable = project.is_publishable()
    url_prefix = notification.get_url_prefix(request)
    publish_form = forms.PublishForm(project=project)

    return render(request, 'console/publish_submission.html',
        {'project': project, 'publishable': publishable, 'authors': authors,
         'author_emails': author_emails, 'storage_info': storage_info,
         'edit_logs': edit_logs, 'copyedit_logs': copyedit_logs,
         'latest_version': latest_version, 'publish_form': publish_form,
         'max_slug_length': MAX_PROJECT_SLUG_LENGTH, 'url_prefix': url_prefix,
         'reassign_editor_form': reassign_editor_form, 'editor_home': True})


def process_storage_response(request, storage_response_formset):
    """
    Implement the response to a storage request.
    Helper function to view: storage_requests.
    """
    storage_request_id = int(request.POST['storage_response'])

    for storage_response_form in storage_response_formset:
        # Only process the response that was submitted
        if storage_response_form.instance.id == storage_request_id:
            if storage_response_form.is_valid() and storage_response_form.instance.is_active:
                storage_request = storage_response_form.instance
                storage_request.responder = request.user
                storage_request.response_datetime = timezone.now()
                storage_request.is_active = False
                storage_request.save()

                if storage_request.response:
                    core_project = storage_request.project.core_project
                    core_project.storage_allowance = storage_request.request_allowance * 1024 ** 3
                    core_project.save()

                notification.storage_response_notify(storage_request)
                messages.success(request,
                    'The storage request has been {}'.format(notification.RESPONSE_ACTIONS[storage_request.response]))

@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def storage_requests(request):
    """
    Page for listing and responding to project storage requests
    """
    StorageResponseFormSet = modelformset_factory(StorageRequest,
        fields=('response', 'response_message'),
        widgets={'response':Select(choices=forms.RESPONSE_CHOICES),
                 'response_message':Textarea()}, extra=0)

    if request.method == 'POST':
        storage_response_formset = StorageResponseFormSet(request.POST,
            queryset=StorageRequest.objects.filter(is_active=True))
        process_storage_response(request, storage_response_formset)

    storage_response_formset = StorageResponseFormSet(
        queryset=StorageRequest.objects.filter(is_active=True))

    return render(request, 'console/storage_requests.html',
        {'storage_response_formset': storage_response_formset,
         'storage_requests_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def unsubmitted_projects(request):
    """
    List of unsubmitted projects
    """
    projects = ActiveProject.objects.filter(submission_status=0).order_by(
        'creation_datetime')
    projects = paginate(request, projects, 50)

    return render(request, 'console/unsubmitted_projects.html',
        {'projects': projects, 'unsubmitted_projects_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def published_projects(request):
    """
    List of published projects
    """
    projects = PublishedProject.objects.all().order_by('-publish_datetime')
    projects = paginate(request, projects, 50)
    return render(request, 'console/published_projects.html',
        {'projects': projects, 'published_projects_nav': True})


@associated_task(PublishedProject, 'pid', read_only=True)
@background()
def send_files_to_gcp(pid):
    """
    Schedule a background task to send the files to GCP.
    This function can be runned manually to force a re-send of all the files
    to GCP. It only requires the Project ID.
    """
    project = PublishedProject.objects.get(id=pid)
    exists = utility.check_bucket_exists(project.slug, project.version)
    if exists:
        utility.upload_files(project)
        project.gcp.sent_files = True
        project.gcp.finished_datetime = timezone.now()
        if project.compressed_storage_size:
            project.gcp.sent_zip = True
        project.gcp.save()


def manage_doi_request(request, project):
    """
    Manage a request to register or update a Digital Object Identifier (DOI).

    Args:
        request (obj): The request object.
        project (obj): The project object.

    Returns:
        str: Message indicating outcome of the request.
    """

    # No action needed if (1) the user is trying to register a DOI when one
    # already exists or (2) if there is no DATACITE_PREFIX
    if not settings.DATACITE_PREFIX:
        return """No action taken. To register or update a DOI, add your
            DATACITE_PREFIX to the Django environment file."""
    elif project.core_project.doi and 'create_doi_core' in request.POST:
        return "The DOI was created."
    elif project.doi and 'create_doi_version' in request.POST:
        return "The DOI was created."

    if 'create_doi_core' in request.POST:
        payload = utility.generate_doi_payload(project, core_project=True,
                                               event="publish")
        utility.register_doi(payload, project.core_project)
        message = "The DOI was created."
    elif 'update_doi_core' in request.POST:
        payload = utility.generate_doi_payload(project, core_project=True,
                                               event="publish")
        utility.update_doi(project.core_project.doi, payload)
        message = "The DOI metadata was updated."
    elif 'create_doi_version' in request.POST:
        payload = utility.generate_doi_payload(project, event="publish")
        utility.register_doi(payload, project)
        message = "The DOI was created."
    elif 'update_doi_version' in request.POST:
        payload = utility.generate_doi_payload(project, event="publish")
        utility.update_doi(project.doi, payload)
        message = "The DOI metadata was updated."

    return message


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def manage_published_project(request, project_slug, version):
    """
    Manage a published project
    - Set the DOI field (after doing it in datacite)
    - Create zip of files
    - Deprecate files
    - Create GCP bucket and send files
    """
    try:
        project = PublishedProject.objects.get(slug=project_slug, version=version)
    except PublishedProject.DoesNotExist:
        raise Http404()
    user = request.user
    passphrase = ''
    anonymous_url = project.get_anonymous_url()
    topic_form = forms.TopicForm(project=project)
    topic_form.set_initial()
    deprecate_form = None if project.deprecated_files else forms.DeprecateFilesForm()
    has_credentials = os.path.exists(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    data_access_form = forms.DataAccessForm(project=project)
    contact_form = forms.PublishedProjectContactForm(project=project,
                                                     instance=project.contact)
    legacy_author_form = forms.CreateLegacyAuthorForm(project=project)

    if request.method == 'POST':
        if any(x in request.POST for x in ['create_doi_core',
                                           'create_doi_version',
                                           'update_doi_core',
                                           'update_doi_version']):
            message = manage_doi_request(request, project)
            messages.success(request, message)
        elif 'set_topics' in request.POST:
            topic_form = forms.TopicForm(project=project, data=request.POST)
            if topic_form.is_valid():
                project.set_topics(topic_form.topic_descriptions)
                # Set the topics
                messages.success(request, 'The topics have been set')
            else:
                messages.error(request, 'Invalid submission. See form below.')
        elif 'make_checksum_file' in request.POST:
            if any(get_associated_tasks(project)):
                messages.error(request, 'Project has tasks pending.')
            elif settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
                raise ServiceUnavailable()
            else:
                make_checksum_background(
                    pid=project.id,
                    verbose_name='Making checksum file - {}'.format(project))
                messages.success(
                    request, 'The files checksum list has been scheduled.')
        elif 'make_zip' in request.POST:
            if any(get_associated_tasks(project)):
                messages.error(request, 'Project has tasks pending.')
            elif settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
                raise ServiceUnavailable()
            else:
                make_zip_background(
                    pid=project.id,
                    verbose_name='Making zip file - {}'.format(project))
                messages.success(
                    request, 'The zip of the main files has been scheduled.')
        elif 'deprecate_files' in request.POST and not project.deprecated_files:
            deprecate_form = forms.DeprecateFilesForm(data=request.POST)
            if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
                raise ServiceUnavailable()
            elif deprecate_form.is_valid():
                project.deprecate_files(
                    delete_files=int(deprecate_form.cleaned_data['delete_files']))
                messages.success(request, 'The project files have been deprecated.')
        elif 'bucket' in request.POST and has_credentials:
            if any(get_associated_tasks(project, read_only=False)):
                messages.error(request, 'Project has tasks pending.')
            else:
                gcp_bucket_management(request, project, user)
        elif 'platform' in request.POST:
            data_access_form = forms.DataAccessForm(project=project, data=request.POST)
            if data_access_form.is_valid():
                data_access_form.save()
                messages.success(request, "Stored method to access the files")
        elif 'data_access_removal' in request.POST and request.POST['data_access_removal'].isdigit():
            try:
                data_access = DataAccess.objects.get(project=project, id=request.POST['data_access_removal'])
                data_access.delete()
                # Deletes the object if it exists for that specific project.
            except DataAccess.DoesNotExist:
                pass
        elif 'generate_passphrase' in request.POST:
            anonymous_url, passphrase = project.generate_anonymous_access()
        elif 'remove_passphrase' in request.POST:
            project.anonymous.all().delete()
            anonymous_url = ''
        elif 'set_contact' in request.POST:
            contact_form = forms.PublishedProjectContactForm(
                instance=project.contact, project=project, data=request.POST)
            if contact_form.is_valid():
                contact_form.save()
                messages.success(request, 'The contact information has been updated')
        elif 'set_legacy_author' in request.POST:
            legacy_author_form = forms.CreateLegacyAuthorForm(project=project,
                                                              data=request.POST)
            if legacy_author_form.is_valid():
                legacy_author_form.save()
                legacy_author_form = forms.CreateLegacyAuthorForm(project=project)

    data_access = DataAccess.objects.filter(project=project)
    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()

    tasks = list(get_associated_tasks(project))
    ro_tasks = [task for (task, read_only) in tasks if read_only]
    rw_tasks = [task for (task, read_only) in tasks if not read_only]

    url_prefix = notification.get_url_prefix(request)

    return render(request, 'console/manage_published_project.html',
        {'project': project, 'authors': authors, 'author_emails': author_emails,
         'storage_info': storage_info, 'edit_logs': edit_logs,
         'copyedit_logs': copyedit_logs, 'latest_version': latest_version,
         'published': True, 'topic_form': topic_form,
         'deprecate_form': deprecate_form, 'has_credentials': has_credentials, 
         'data_access_form': data_access_form, 'data_access': data_access,
         'rw_tasks': rw_tasks, 'ro_tasks': ro_tasks,
         'anonymous_url': anonymous_url, 'passphrase': passphrase,
         'published_projects_nav': True, 'url_prefix': url_prefix,
         'contact_form': contact_form,
         'legacy_author_form': legacy_author_form})


def gcp_bucket_management(request, project, user):
    """
    Create the database object and cloud bucket if they do not exist, and send
    the files to the bucket.
    """
    is_private = True

    if project.access_policy == 0:
        is_private = False

    bucket_name, group = utility.bucket_info(project.slug, project.version)

    try:
        gcp_object = GCP.objects.get(bucket_name=bucket_name)
        messages.success(request, "The bucket already exists. Resending the \
            files for the project {0}.".format(project))
    except GCP.DoesNotExist:
        if utility.check_bucket_exists(project.slug, project.version):
            LOGGER.info("The bucket {0} already exists, skipping bucket and \
                group creation".format(bucket_name))
        else:
            utility.create_bucket(project.slug, project.version, project.title, is_private)
            messages.success(request, "The GCP bucket for project {0} was \
                successfully created.".format(project))
        GCP.objects.create(project=project, bucket_name=bucket_name,
            managed_by=user, is_private=is_private, access_group=group)
        if is_private:
            granted = utility.add_email_bucket_access(project, group, True)
            DataAccess.objects.create(project=project, platform=3, location=group)
            if not granted:
                error = "The GCP bucket for project {0} was successfully created, \
                    but there was an error granting read permissions to the \
                    group: {1}".format(project, group)
                messages.success(request, error)
                raise Exception(error)
            messages.success(request, "The access group for project {0} was \
                successfully added.".format(project))

    send_files_to_gcp(project.id, verbose_name='GCP - {}'.format(project), creator=user)


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def rejected_submissions(request):
    """
    List of rejected submissions
    """
    projects = ArchivedProject.objects.filter(archive_reason=3).order_by('archive_datetime')
    projects = paginate(request, projects, 50)
    return render(request, 'console/rejected_submissions.html',
        {'projects': projects, 'rejected_projects_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def users(request, group='all'):
    """
    List of users
    """
    show_inactive = False
    if group == 'admin':
        admin_users = User.objects.filter(is_admin=True).order_by('username')
        return render(request, 'console/users_admin.html', {
            'admin_users': admin_users, 'group': group, 'user_nav': True})
    elif group == 'active':
        user_list = User.objects.filter(is_active=True).order_by('username')
    elif group == 'inactive':
        user_list = User.objects.filter(is_active=False).order_by('username')
    else:
        user_list = User.objects.all().order_by('username')
        show_inactive = True
    users = paginate(request, user_list, 50)

    return render(request, 'console/users.html', {'users': users,
        'show_inactive': show_inactive, 'group': group, 'user_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def user_management(request, username):
    """
    Admin page for managing an individual user account.
    """
    user = get_object_or_404(User, username__iexact=username)

    emails = {}
    emails['primary'] = AssociatedEmail.objects.filter(user=user,
                                                       is_primary_email=True,
                                                       is_verified=True)
    emails['other'] = AssociatedEmail.objects.filter(user=user,
                                                     is_primary_email=False,
                                                     is_verified=True)
    emails['unverified'] = AssociatedEmail.objects.filter(user=user,
                                                          is_verified=False)

    projects = {}
    projects['Unsubmitted'] = ActiveProject.objects.filter(authors__user=user,
                                submission_status=0).order_by('-creation_datetime')
    projects['Submitted'] = ActiveProject.objects.filter(authors__user=user,
                                submission_status__gt=0).order_by('-submission_datetime')
    projects['Archived'] = ArchivedProject.objects.filter(authors__user=user).order_by('-archive_datetime')
    projects['Published'] = PublishedProject.objects.filter(authors__user=user).order_by('-publish_datetime')


    return render(request, 'console/user_management.html', {'subject': user,
                                                            'profile': user.profile,
                                                            'emails': emails,
                                                            'projects': projects})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def users_search(request, group):
    """
    Search user list.

    Args:
        group (str): group of users to filter search. Either 'all' for all users or 
            'inactive' to filter to inactive users only.
    """

    if request.method == 'POST':
        search_field = request.POST['search']

        users = User.objects.filter(Q(username__icontains=search_field) |
            Q(profile__first_names__icontains=search_field) |
            Q(email__icontains=search_field))

        if 'inactive' in group:
            users = users.filter(is_active=False)
        elif 'active' in group:
            users = users.filter(is_active=True)

        users = users.order_by('username')

        if len(search_field) == 0:
            users = paginate(request, users, 50)

        return render(request, 'console/users_list.html', {'users':users,
            'group': group})

    raise Http404()


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def known_references_search(request):
    """
    Search credential applications and user list.
    """

    if request.method == 'POST':
        search_field = request.POST['search']

        applications = CredentialApplication.objects.filter(
            Q(reference_email__icontains=search_field) |
            Q(reference_name__icontains=search_field) |
            Q(user__profile__last_name__icontains=search_field) |
            Q(user__profile__first_names__icontains=search_field))

        all_known_ref = applications.exclude(
            reference_contact_datetime__isnull=True).order_by(
            '-reference_contact_datetime')

        if len(search_field) == 0:
            all_known_ref = paginate(request, all_known_ref, 50)

        return render(request, 'console/known_references_list.html', {
            'all_known_ref': all_known_ref})

    raise Http404()


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def credential_applications(request):
    """
    Ongoing credential applications
    """
    applications = CredentialApplication.objects.filter(status=0)
    applications = applications.order_by('application_datetime')

    return render(request, 'console/credential_applications.html',
        {'applications': applications, 'credentials_nav': True})

@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def complete_credential_applications(request):
    """
    KP's custom management page for credentialing.
    """
    process_credential_form = forms.ProcessCredentialForm(
        responder=request.user)

    if request.method == 'POST':
        if 'contact_reference' in request.POST and \
         request.POST['contact_reference'].isdigit():
            application_id = request.POST.get('contact_reference', '')
            application = CredentialApplication.objects.get(id=application_id)
            if not application.reference_contact_datetime:
                application.reference_contact_datetime = timezone.now()
                application.save()
            # notification.contact_reference(request, application)
            if application.reference_category == 0:
                mailto = notification.mailto_supervisor(request, application)
            else:
                mailto = notification.mailto_reference(request, application)
            # messages.success(request, 'The reference contact email has
            #                  been created.')
            return render(request, 'console/generate_reference_email.html',
                          {'application': application, 'mailto': mailto})
        if 'process_application' in request.POST and \
         request.POST['process_application'].isdigit():
            application_id = request.POST.get('process_application', '')
            try:
                application = CredentialApplication.objects.get(
                    id=application_id, status=0)
            except CredentialApplication.DoesNotExist:
                messages.error(request, """The application has already been
                    processed. It may have been withdrawn by the applicant or
                    handled by another administrator.""")
                return redirect('complete_credential_applications')
            process_credential_form = forms.ProcessCredentialForm(
                responder=request.user, data=request.POST,
                instance=application)

            if process_credential_form.is_valid():
                application = process_credential_form.save()
                notification.process_credential_complete(request, application,
                                                         comments=False)
                mailto = notification.mailto_process_credential_complete(
                    request, application)
                return render(request, 'console/generate_response_email.html',
                              {'application': application, 'mailto': mailto})
            else:
                messages.error(request, 'Invalid submission. See form below.')

    applications = CredentialApplication.objects.filter(status=0)

    # TODO: Remove this step. Exclude applications that are being handled in
    # the credential processing workflow. Avoid toes.
    review_underway_list = [x[0] for x in CredentialReview.REVIEW_STATUS_LABELS
                            if x[0] and x[0] > 10]
    review_underway = Q(credential_review__status__in=review_underway_list)
    applications = applications.exclude(review_underway)

    # Get list of references who have been contacted before
    # These are "known_refs" but using the ref_known_flag() method is slow
    known_refs_new = CredentialApplication.objects.filter(
        reference_contact_datetime__isnull=False).values_list(
        'reference_email', flat=True)
    known_refs_legacy = LegacyCredential.objects.exclude(
        reference_email='').values_list('reference_email', flat=True)

    known_refs = set(known_refs_new).union(set(known_refs_legacy))
    known_refs = [x.lower() for x in known_refs if x]

    # Group applications and sort by application date
    # 1. reference not contacted, but with reference known
    known_ref_no_contact = applications.filter(
        reference_contact_datetime__isnull=True,
        reference_email__in=known_refs).order_by('application_datetime')

    # 2. reference not contacted, but with reference unknown
    unknown_refs = [x.reference_email for x in applications
                    if x.reference_email not in known_refs]
    unknown_ref_no_contact = applications.filter(
        reference_contact_datetime__isnull=True,
        reference_email__in=unknown_refs).order_by('application_datetime')

    # 3. reference contacted
    contacted = applications.filter(
        reference_contact_datetime__isnull=False).order_by('application_datetime')

    applications = (list(known_ref_no_contact) +
                    list(unknown_ref_no_contact) +
                    list(contacted))

    return render(request, 'console/complete_credential_applications.html',
                  {'process_credential_form': process_credential_form,
                   'applications': applications, 'known_refs': known_refs,
                   'complete_credentials_nav': True})

@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def complete_list_credentialed_people(request):
    legacy_cred_user = LegacyCredential.objects.all().order_by('-mimic_approval_date')
    new_cred_user = CredentialApplication.objects.filter(status=2).order_by('-decision_datetime')

    credentialed_people = []
    for item in legacy_cred_user:
        try:
            credentialed_people.append([item.first_names, item.last_name,
                item.email, item.country, datetime.strptime(item.mimic_approval_date, '%m/%d/%Y'),
                datetime.strptime(item.eicu_approval_date, '%m/%d/%Y'), item.info])
        except ValueError:
            credentialed_people.append([item.first_names, item.last_name,
                item.email, item.country, datetime.strptime(item.mimic_approval_date, '%m/%d/%Y'),
                None, item.info])
    for item in new_cred_user:
        credentialed_people.append([item.first_names, item.last_name, 
            item.user.email, item.country, item.decision_datetime.replace(tzinfo=None), 
            item.decision_datetime.replace(tzinfo=None), item.research_summary])

    credentialed_people = sorted(credentialed_people, key = lambda x: x[4])
    return render(request, 'console/complete_list_credentialed_people.html',
        {'credentialed_people': credentialed_people})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def process_credential_application(request, application_slug):
    """
    Process a credential application. View details, advance to next stage,
    contact reference, and make final decision.
    """
    try:
        application = CredentialApplication.objects.get(slug=application_slug,
            status=0)
        # create the review object if it does not exist
        CredentialReview.objects.get_or_create(application=application)
    except CredentialApplication.DoesNotExist:
        messages.error(request, """The application has already been
            processed. It may have been withdrawn by the applicant or
            handled by another administrator.""")
        return redirect('credential_applications')

    process_credential_form = forms.ProcessCredentialReviewForm(responder=request.user,
        instance=application)

    ref_email = notification.contact_reference(request, application,
                                               send=False,  wordwrap=False)
    contact_cred_ref_form = forms.ContactCredentialRefForm(initial=ref_email)

    try:
        ref = User.objects.get(associated_emails__email__iexact=application.reference_email,
                               associated_emails__is_verified=True)
        known_active = True
        known_cred = ref.is_credentialed
    except ObjectDoesNotExist:
        known_active = False
        known_cred = False

    page_title = None
    title_dict = {a: k for a, k in CredentialReview.REVIEW_STATUS_LABELS}
    page_title = title_dict[application.credential_review.status]
    if application.credential_review.status == 10:
        intermediate_credential_form = forms.InitialCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 20:
        intermediate_credential_form = forms.TrainingCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 30:
        intermediate_credential_form = forms.PersonalCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 40:
        intermediate_credential_form = forms.ReferenceCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 50:
        intermediate_credential_form = forms.ResponseCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 60:
        intermediate_credential_form = forms.ProcessCredentialReviewForm(responder=request.user, instance=application)

    if request.method == 'POST':
        if 'approve_initial' in request.POST:
            intermediate_credential_form = forms.InitialCredentialForm(
                responder=request.user, data=request.POST, instance=application)
            if intermediate_credential_form.is_valid():
                intermediate_credential_form.save()
                if intermediate_credential_form.cleaned_data['decision'] == '0':
                    notification.process_credential_complete(request,
                                                             application)
                    return render(request, 'console/process_credential_complete.html',
                        {'application':application})
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.TrainingCredentialForm(
                    responder=request.user, instance=application)
            else:
                messages.error(request, 'Invalid review. See form below.')
        elif 'approve_initial_all' in request.POST:
            if request.POST['decision'] == '0':
                messages.error(request, 'You selected Reject. Did you mean to Approve All?')
            else:
                data_copy = request.POST.copy()
                valid_fields = set(request.POST.keys())
                valid_fields.difference_update({'csrfmiddlewaretoken',
                                                'responder_comments',
                                                'approve_initial_all'})
                for field in valid_fields:
                    data_copy[field] = '1'
                intermediate_credential_form = forms.InitialCredentialForm(
                    responder=request.user, data=data_copy, instance=application)
                intermediate_credential_form.save()
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.TrainingCredentialForm(
                    responder=request.user, instance=application)
        elif 'approve_training' in request.POST:
            intermediate_credential_form = forms.TrainingCredentialForm(
                responder=request.user, data=request.POST, instance=application)
            if intermediate_credential_form.is_valid():
                intermediate_credential_form.save()
                if intermediate_credential_form.cleaned_data['decision'] == '0':
                    notification.process_credential_complete(request,
                                                             application)
                    return render(request, 'console/process_credential_complete.html',
                        {'application':application})
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.PersonalCredentialForm(
                    responder=request.user, instance=application)
            else:
                messages.error(request, 'Invalid review. See form below.')
        elif 'approve_training_all' in request.POST:
            if request.POST['decision'] == '0':
                messages.error(request, 'You selected Reject. Did you mean to Approve All?')
            else:
                data_copy = request.POST.copy()
                valid_fields = set(request.POST.keys())
                valid_fields.difference_update({'csrfmiddlewaretoken',
                                                'responder_comments',
                                                'approve_training_all'})
                for field in valid_fields:
                    data_copy[field] = '1'
                intermediate_credential_form = forms.TrainingCredentialForm(
                    responder=request.user, data=data_copy, instance=application)
                intermediate_credential_form.save()
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.PersonalCredentialForm(
                    responder=request.user, instance=application)
        elif 'approve_personal' in request.POST:
            intermediate_credential_form = forms.PersonalCredentialForm(
                responder=request.user, data=request.POST, instance=application)
            if intermediate_credential_form.is_valid():
                intermediate_credential_form.save()
                if intermediate_credential_form.cleaned_data['decision'] == '0':
                    notification.process_credential_complete(request,
                                                             application)
                    return render(request, 'console/process_credential_complete.html',
                        {'application':application})
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ReferenceCredentialForm(
                    responder=request.user, instance=application)
            else:
                messages.error(request, 'Invalid review. See form below.')
        elif 'approve_personal_all' in request.POST:
            if request.POST['decision'] == '0':
                messages.error(request, 'You selected Reject. Did you mean to Approve All?')
            else:
                data_copy = request.POST.copy()
                valid_fields = set(request.POST.keys())
                valid_fields.difference_update({'csrfmiddlewaretoken',
                                                'responder_comments',
                                                'approve_personal_all'})
                for field in valid_fields:
                    data_copy[field] = '1'
                intermediate_credential_form = forms.PersonalCredentialForm(
                    responder=request.user, data=data_copy, instance=application)
                intermediate_credential_form.save()
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ReferenceCredentialForm(
                    responder=request.user, instance=application)
        elif 'approve_reference' in request.POST:
            intermediate_credential_form = forms.ReferenceCredentialForm(
                responder=request.user, data=request.POST, instance=application)
            if intermediate_credential_form.is_valid():
                intermediate_credential_form.save()
                if intermediate_credential_form.cleaned_data['decision'] == '0':
                    notification.process_credential_complete(request,
                                                             application)
                    return render(request, 'console/process_credential_complete.html',
                        {'application':application})
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ResponseCredentialForm(
                    responder=request.user, instance=application)
            else:
                messages.error(request, 'Invalid review. See form below.')
        elif 'approve_reference_all' in request.POST:
            if request.POST['decision'] == '0':
                messages.error(request, 'You selected Reject. Did you mean to Approve All?')
            else:
                data_copy = request.POST.copy()
                valid_fields = set(request.POST.keys())
                valid_fields.difference_update({'csrfmiddlewaretoken',
                                                'responder_comments',
                                                'approve_reference_all'})
                for field in valid_fields:
                    data_copy[field] = '1'
                intermediate_credential_form = forms.ReferenceCredentialForm(
                    responder=request.user, data=data_copy, instance=application)
                intermediate_credential_form.save()
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ResponseCredentialForm(
                    responder=request.user, instance=application)
        elif 'approve_response' in request.POST:
            intermediate_credential_form = forms.ResponseCredentialForm(
                responder=request.user, data=request.POST, instance=application)
            if intermediate_credential_form.is_valid():
                intermediate_credential_form.save()
                if intermediate_credential_form.cleaned_data['decision'] == '0':
                    notification.process_credential_complete(request,
                                                             application)
                    return render(request, 'console/process_credential_complete.html',
                        {'application':application})
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ProcessCredentialReviewForm(
                    responder=request.user, instance=application)
            else:
                messages.error(request, 'Invalid review. See form below.')
        elif 'approve_response_all' in request.POST:
            if request.POST['decision'] == '0':
                messages.error(request, 'You selected Reject. Did you mean to Approve All?')
            else:
                data_copy = request.POST.copy()
                valid_fields = set(request.POST.keys())
                valid_fields.difference_update({'csrfmiddlewaretoken',
                                                'responder_comments',
                                                'approve_response_all'})
                for field in valid_fields:
                    data_copy[field] = '1'
                intermediate_credential_form = forms.ResponseCredentialForm(
                    responder=request.user, data=data_copy, instance=application)
                intermediate_credential_form.save()
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ProcessCredentialReviewForm(
                    responder=request.user, instance=application)
        elif 'contact_reference' in request.POST:
            contact_cred_ref_form = forms.ContactCredentialRefForm(
                data=request.POST)
            if contact_cred_ref_form.is_valid():
                application.reference_contact_datetime = timezone.now()
                application.save()
                subject = contact_cred_ref_form.cleaned_data['subject']
                body = contact_cred_ref_form.cleaned_data['body']
                notification.contact_reference(request, application,
                                               subject=subject, body=body)
                messages.success(request, 'The reference has been contacted.')
        elif 'skip_reference' in request.POST:
            application.update_review_status(60)
            application.save()
        elif 'process_application' in request.POST:
            process_credential_form = forms.ProcessCredentialReviewForm(
                responder=request.user, data=request.POST, instance=application)
            if process_credential_form.is_valid():
                application = process_credential_form.save()
                notification.process_credential_complete(request, application)
                return render(request, 'console/process_credential_complete.html',
                    {'application':application})
            else:
                messages.error(request, 'Invalid submission. See form below.')
    return render(request, 'console/process_credential_application.html',
        {'application': application, 'app_user': application.user,
         'intermediate_credential_form': intermediate_credential_form,
         'process_credential_form': process_credential_form,
         'processing_credentials_nav': True, 'page_title': page_title,
         'contact_cred_ref_form': contact_cred_ref_form,
         'known_active': known_active, 'known_cred': known_cred})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def credential_processing(request):
    """
    Process applications for credentialed access.
    """
    applications = CredentialApplication.objects.filter(status=0)

    # TODO: Remove this step. If KP has contacted the reference, exclude the
    # application from our list. Avoid toes.
    no_review = Q(credential_review__isnull=True)
    ref_contacted = Q(reference_contact_datetime__isnull=False)
    applications = applications.exclude(no_review, ref_contacted)

    # Awaiting initial review
    initial_1 = Q(credential_review__isnull=True)
    initial_2 = Q(credential_review__status=10)
    initial_applications = applications.filter(
        initial_1 | initial_2).order_by('application_datetime')
    # Awaiting training check
    training_applications = applications.filter(
        credential_review__status=20).order_by('application_datetime')
    # Awaiting ID check
    personal_applications = applications.filter(
        credential_review__status=30).order_by('application_datetime')
    # Awaiting reference check
    reference_applications = applications.filter(
        credential_review__status=40).order_by('application_datetime')
    # Awaiting reference response
    response_applications = applications.filter(
        credential_review__status=50).order_by('application_datetime')
    # Awaiting final review
    final_applications = applications.filter(
        credential_review__status=60).order_by('application_datetime')

    return render(request, 'console/credential_processing.html',
        {'applications': applications,
        'initial_applications': initial_applications,
        'training_applications': training_applications,
        'personal_applications': personal_applications,
        'reference_applications': reference_applications,
        'response_applications': response_applications,
        'final_applications': final_applications,
        'processing_credentials_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def view_credential_application(request, application_slug):
    """
    View a credential application in any status.
    """
    try:
        application = CredentialApplication.objects.get(slug=application_slug)
    except CredentialApplication.DoesNotExist:
        raise Http404()

    form = forms.AlterCommentsCredentialForm(initial={
        'responder_comments': application.responder_comments})
    if request.method == 'POST':
        form = forms.AlterCommentsCredentialForm(data=request.POST,
                                                 instance=application)
        if form.is_valid():
            form.save()

    return render(request, 'console/view_credential_application.html',
                  {'application': application, 'app_user': application.user,
                   'form': form, 'past_credentials_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def past_credential_applications(request, status):
    """
    Inactive credential applications. Split into successful and
    unsuccessful.
    """
    if request.method == 'POST':
        if 'remove_credentialing' in request.POST:
            if request.POST['remove_credentialing'].isdigit():
                cid = request.POST['remove_credentialing']
                c_application = CredentialApplication.objects.filter(id=cid)
                if c_application:
                    c_application = c_application.get()
                    c_application.revoke()
            else:
                l_application = LegacyCredential.objects.filter(email=request.POST['remove_credentialing'])
                if l_application:
                    l_application = l_application.get()
                    l_application.revoke()
        elif 'manage_credentialing' in request.POST and request.POST['manage_credentialing'].isdigit():
            cid = request.POST['manage_credentialing']
            c_application = CredentialApplication.objects.filter(id=cid)
            if c_application:
                c_application = c_application.get()
                c_application.status = 0
                c_application.save()
        elif "search" in request.POST:
            (all_successful_apps, unsuccessful_apps,
                processing_apps) = search_credential_applications(request)
            if status == 'successful':
                return render(request, 'console/past_credential_successful_user_list.html',
                    {'applications': all_successful_apps,
                     'u_applications': unsuccessful_apps,
                     'p_applications': processing_apps})
            elif status == 'unsuccessful':
                return render(request, 'console/past_credential_unsuccessful_user_list.html',
                    {'applications': all_successful_apps,
                     'u_applications': unsuccessful_apps,
                     'p_applications': processing_apps})
            elif status == 'processing':
                return render(request, 'console/past_credential_processing_user_list.html',
                    {'applications': all_successful_apps,
                     'u_applications': unsuccessful_apps,
                     'p_applications': processing_apps})

    legacy_apps = LegacyCredential.objects.filter(migrated=True,
        migrated_user__is_credentialed=True).order_by('-migration_date')

    successful_apps = CredentialApplication.objects.filter(status=2
        ).order_by('-decision_datetime')
    unsuccessful_apps = CredentialApplication.objects.filter(
        status__in=[1, 3, 4]).order_by('-decision_datetime')
    processing_apps = CredentialApplication.objects.filter(status=0
        ).order_by('-application_datetime')

    # Merge legacy applications and new applications
    all_successful_apps = list(chain(successful_apps, legacy_apps))

    all_successful_apps = paginate(request, all_successful_apps, 50)
    unsuccessful_apps = paginate(request, unsuccessful_apps, 50)
    processing_apps = paginate(request, processing_apps, 50)

    return render(request, 'console/past_credential_applications.html',
        {'applications': all_successful_apps, 'past_credentials_nav': True,
         'u_applications': unsuccessful_apps,
         'p_applications': processing_apps})


def search_credential_applications(request):
    """
    Search past credentialing applications.

    Args:
        request (obj): Django WSGIRequest object.
    """
    if request.POST:
        search_field = request.POST['search']

        legacy_apps = LegacyCredential.objects.filter(Q(migrated=True) &
            Q(migrated_user__is_credentialed=True) &
            (Q(migrated_user__username__icontains=search_field) |
            Q(migrated_user__profile__first_names__icontains=search_field) |
            Q(migrated_user__email__icontains=search_field))).order_by('-migration_date')

        successful_apps = CredentialApplication.objects.filter(
            Q(status=2) & (Q(user__username__icontains=search_field) |
            Q(user__profile__first_names__icontains=search_field) |
            Q(user__email__icontains=search_field))).order_by('-application_datetime')

        unsuccessful_apps = CredentialApplication.objects.filter(
            Q(status__in=[1, 3]) & (Q(user__username__icontains=search_field) |
            Q(user__profile__first_names__icontains=search_field) |
            Q(user__email__icontains=search_field))).order_by('-application_datetime')

        processing_apps = CredentialApplication.objects.filter(
            Q(status=0) & (Q(user__username__icontains=search_field) |
            Q(user__profile__first_names__icontains=search_field) |
            Q(user__email__icontains=search_field))).order_by('-application_datetime')

        # Merge legacy applications with new applications
        all_successful_apps = list(chain(successful_apps, legacy_apps))

        if len(search_field) == 0:
            all_successful_apps = paginate(request, all_successful_apps, 50)
            unsuccessful_apps = paginate(request, unsuccessful_apps, 50)
            processing_apps = paginate(request, processing_apps, 50)

        return all_successful_apps, unsuccessful_apps, processing_apps


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def credentialed_user_info(request, username):
    try:
        c_user = User.objects.get(username__iexact=username)
        application = CredentialApplication.objects.get(user=c_user, status=2)
    except (User.DoesNotExist, CredentialApplication.DoesNotExist):
        raise Http404()
    return render(request, 'console/credentialed_user_info.html',
        {'c_user':c_user, 'application':application})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def news_console(request):
    """
    List of news items
    """
    news_items = News.objects.all().order_by('-publish_datetime')
    news_items = paginate(request, news_items, 50)
    return render(request, 'console/news_console.html', 
        {'news_items': news_items, 'news_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def news_add(request):
    if request.method == 'POST':
        form = forms.NewsForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'The news item has been added')
            return redirect('news_console')
    else:
        form = forms.NewsForm()

    return render(request, 'console/news_add.html', {'form': form,
        'news_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def news_search(request):
    """
    Filtered list of news items
    """

    if request.method == 'POST':
        search = request.POST['search']
        news_items = News.objects.filter(title__icontains=search).order_by('-publish_datetime')

        return render(request, 'console/news_list.html', {'news_items':news_items})

    raise Http404()


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def news_edit(request, news_id):
    try:
        news = News.objects.get(id=news_id)
    except News.DoesNotExist:
        raise Http404()
    if request.method == 'POST':
        if 'update' in request.POST:
            form = forms.NewsForm(data=request.POST, instance=news)
            if form.is_valid():
                form.save()
                messages.success(request, 'The news item has been updated')
        elif 'delete' in request.POST:
            news.delete()
            messages.success(request, 'The news item has been deleted')
            return redirect('news_console')
    else:
        form = forms.NewsForm(instance=news)

    return render(request, 'console/news_edit.html', {'news': news,
        'form': form, 'news_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def featured_content(request):
    """
    List of news items
    """

    if 'add' in request.POST:
        featured = PublishedProject.objects.filter(featured__isnull=False)
        mx = max(featured.values_list('featured', flat=True), default=1)
        project = PublishedProject.objects.filter(id=request.POST['id']).update(featured=mx+1)
    elif 'remove' in request.POST:
        project = PublishedProject.objects.filter(id=request.POST['id']).update(featured=None)
    elif 'up' in request.POST:
        # Get project to be moved
        idx = int(request.POST['up'])
        move = PublishedProject.objects.get(featured=idx)

        # Sets featured to 0 (avoid constraint violation)
        move.featured = 0
        move.save()

        # Swap positions
        PublishedProject.objects.filter(featured=idx-1).update(featured=idx)
        move.featured = idx-1
        move.save()
    elif 'down' in request.POST:
        # Get project to be moved
        idx = int(request.POST['down'])
        move = PublishedProject.objects.get(featured=idx)

        # Sets featured to 0 (avoid constraint violation)
        move.featured = 0
        move.save()

        # Swap positions
        PublishedProject.objects.filter(featured=idx+1).update(featured=idx)
        move.featured = idx+1
        move.save()


    featured_content = PublishedProject.objects.filter(featured__isnull=False).order_by('featured')

    return render(request, 'console/featured_content.html',
        {'featured_content': featured_content, 'featured_content_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def add_featured(request):
    """
    List of news items
    """
    title, valid_search, projects = '', False, None
    # If we get a form submission, redirect to generate the querystring
    # in the url
    if 'title' in request.GET:
        form = forms.FeaturedForm(request.GET)
        if form.is_valid():
            title = form.cleaned_data['title']
            valid_search = True

        # Word boundary for different database engines
        wb = r'\b'
        if 'postgresql' in settings.DATABASES['default']['ENGINE']:
            wb = r'\y'

        projects = PublishedProject.objects.filter(
            title__iregex=r'{0}{1}{0}'.format(wb,title),
            featured__isnull=True
        )
    else:
        form = forms.FeaturedForm()

    return render(request, 'console/add_featured.html', {'title': title,
        'projects': projects, 'form': form, 'valid_search': valid_search,
        'featured_content_nav': True})

@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def guidelines_review(request):
    """
    Guidelines for reviewers.
    """
    return render(request, 'console/guidelines_review.html',
        {'guidelines_review_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def editorial_stats(request):
    """
    Editorial stats for reviewers.
    """
    # We only want the non-legacy projects since they contain the required
    # dates (editor assignment, submission date, etc.)
    projects = PublishedProject.objects.filter(is_legacy=False)
    years = [i.publish_datetime.year for i in projects]
    stats = OrderedDict()

    # Number published
    for y in sorted(set(years)):
        stats[y] = [years.count(y)]

    # Submission to editor assigned
    sub_ed = projects.annotate(tm=Cast(F('editor_assignment_datetime')-F('submission_datetime'),
                               DurationField())).values_list('tm', flat=True)

    for y in stats:
        y_durations = sub_ed.filter(publish_datetime__year=y)
        days = [d.days for d in y_durations if d.days >= 0]
        try:
            stats[y].append(median(days))
        except StatisticsError:
            stats[y].append(None)

    # Submission to publication
    sub_pub = projects.annotate(tm=Cast(F('publish_datetime')-F('submission_datetime'),
                                DurationField())).values_list('tm', flat=True)

    for y in stats:
        y_durations = sub_pub.filter(publish_datetime__year=y)
        days = [d.days for d in y_durations if d.days >= 0]
        try:
            stats[y].append(median(days))
        except StatisticsError:
            stats[y].append(None)

    return render(request, 'console/editorial_stats.html', {'stats_nav': True,
                  'submenu': 'editorial', 'stats': stats})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def credentialing_stats(request):
    """
    Credentialing metrics.
    """
    apps = CredentialApplication.objects.all()
    years = [a.application_datetime.year for a in apps]
    stats = OrderedDict()

    # Application count by year
    for y in sorted(set(years)):
        stats[y] = {}
        stats[y]['count'] = years.count(y)

    # Number processed (accepted or rejected) and proportion approved
    for y in stats:
        # accepted = 2. rejected = 1.
        acc_and_rej = apps.filter(application_datetime__year=y)
        a = acc_and_rej.filter(status=2).count()
        r = acc_and_rej.filter(status=1).count()
        stats[y]['processed'] = a + r
        stats[y]['approved'] = round((100 * a) / (a + r))

    # Time taken to contact the reference
    time_to_ref = apps.annotate(tm=Cast(F('reference_contact_datetime') -
                                F('application_datetime'),
                                DurationField())).values_list('tm', flat=True)
    for y in stats:
        durations = time_to_ref.filter(application_datetime__year=y)
        try:
            days = [d.days for d in durations if d and d.days >= 0]
            stats[y]['time_to_ref'] = median(days)
        except (AttributeError, StatisticsError):
            stats[y]['time_to_ref'] = None

    # Time taken for the reference to respond
    time_to_reply = apps.annotate(tm=Cast(F('reference_response_datetime') -
                                  F('reference_contact_datetime'),
                                  DurationField())).values_list('tm', flat=True)
    for y in stats:
        durations = time_to_reply.filter(application_datetime__year=y)
        try:
            days = [d.days for d in durations if d and d.days >= 0]
            stats[y]['time_to_reply'] = median(days)
        except (AttributeError, StatisticsError):
            stats[y]['time_to_reply'] = None

    # Time taken to process the application
    time_to_decision = apps.annotate(tm=Cast(F('decision_datetime') -
                                     F('application_datetime'),
                                     DurationField())).values_list('tm', flat=True)
    for y in stats:
        durations = time_to_decision.filter(application_datetime__year=y)
        try:
            days = [d.days for d in durations if d and d.days >= 0]
            stats[y]['time_to_decision'] = median(days)
        except (AttributeError, StatisticsError):
            stats[y]['time_to_decision'] = None

    return render(request, 'console/credentialing_stats.html',
                  {'stats_nav': True, 'submenu': 'credential',
                   'stats': stats})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def download_credentialed_users(request):
    """
    CSV create and download for database access.
    """
    # Create the HttpResponse object with the appropriate CSV header.
    project_access = DUASignature.objects.filter(project__access_policy = 2)
    added = []
    dua_info_csv = [['First name', 'Last name', 'E-mail', 'Institution', 'Country', 
    'MIMIC approval date', 'eICU approval date', 
    'General research area for which the data will be used']]
    for person in project_access:
        application = person.user.credential_applications.last()
        mimic_signature_date = eicu_signature_date = None
        if 'mimic' in person.project.slug:
            mimic_signature_date = person.sign_datetime
        elif 'eicu' in person.project.slug:
            eicu_signature_date = person.sign_datetime
        if person.user.id in added:
            for indx, item in enumerate(dua_info_csv):
                if item[2] == person.user.email and item[5] == None:
                    dua_info_csv[indx][5] = mimic_signature_date
                elif item[2] == person.user.email and item[6] == None:
                    dua_info_csv[indx][6] = eicu_signature_date
        else:
            if application:
                dua_info_csv.append([person.user.profile.first_names,
                    person.user.profile.last_name, person.user.email,
                    application.organization_name, application.country,
                    mimic_signature_date, eicu_signature_date,
                    application.research_summary])
                added.append(person.user.id)
            else:
                legacy = LegacyCredential.objects.filter(migrated_user_id=person.user.id)
                if legacy:
                    legacy = legacy.get()
                    dua_info_csv.append([person.user.profile.first_names,
                        person.user.profile.last_name, person.user.email,
                        'Legacy User', legacy.country,
                        legacy.mimic_approval_date, legacy.eicu_approval_date,
                        legacy.info])
                    added.append(person.user.id)
                else:
                    LOGGER.info("Failed locating information of user {}".format(
                        person.user.id))


    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="credentialed_users.csv"'
    writer = csv.writer(response)
    for item in dua_info_csv:
        writer.writerow(item)

    return response


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def project_access(request):
    """
    List all the people that has access to credentialed databases
    """
    c_projects = PublishedProject.objects.filter(access_policy=2).annotate(
        member_count=Value(0, IntegerField()))

    for project in c_projects:
        project.member_count = DUASignature.objects.filter(
            project__access_policy = 2, project=project).count()

    return render(request, 'console/project_access.html',
        {'c_projects': c_projects, 'project_access_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def project_access_manage(request, pid):
    c_project = PublishedProject.objects.filter(id=pid)
    if c_project:
        c_project = c_project.get()
        project_members = DUASignature.objects.filter(
            project__access_policy = 2, project=c_project)

        return render(request, 'console/project_access_manage.html', {
            'c_project': c_project, 'project_members': project_members,
            'project_access_nav': True})


class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        """
        Get all active users with usernames that match the request string,
        excluding the user who is doing the search.
        """
        qs = User.objects.filter(is_active=True)

        if self.q:
            qs = qs.filter(username__icontains=self.q)

        return qs

@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def known_references(request):
    """
    List all known references witht he option of removing the contact date
    """
    user = request.user

    if 'remove_known_ref' in request.POST and \
       request.POST['remove_known_ref'].isdigit():
        try:
            application = CredentialApplication.objects.get(
                id=request.POST['remove_known_ref'])
            application.remove_contact_reference()
            LOGGER.info('User {0} removed reference contacted for application \
                {1}'.format(user, application.id))
            messages.success(request, 'The reference contacted has been removed.')
        except CredentialApplication.DoesNotExist:
            pass

    all_known_ref = CredentialApplication.objects.filter(
        reference_contact_datetime__isnull=False).order_by(
        '-reference_contact_datetime')

    all_known_ref = paginate(request, all_known_ref, 50)

    return render(request, 'console/known_references.html', {
        'all_known_ref': all_known_ref, 'known_ref_nav': True})


@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def complete_credential_applications_mailto(request):
    """
    Return the mailto link to a credentialing applicant.
    """
    app_id = request.GET['app_id']
    try:
        app = CredentialApplication.objects.get(id=app_id)
    except CredentialApplication.DoesNotExist:
        return JsonResponse({'mailtolink': 'false'})

    mailto = notification.mailto_process_credential_complete(request, app,
                                                             comments=False)

    return JsonResponse({'mailtolink': mailto})
