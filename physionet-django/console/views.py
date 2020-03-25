import re
import pdb
import logging
import os
import csv
from datetime import datetime
from itertools import chain

from django.core.validators  import validate_email
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.db import DatabaseError, transaction
from django.db.models import Q, CharField, Value, IntegerField, F, functions
from background_task import background
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist

from notification.models import News
import notification.utility as notification
from physionet.utility import paginate
import project.forms as project_forms
from project.models import (ActiveProject, ArchivedProject, StorageRequest,
    Reference, Topic, Publication, PublishedProject,
    exists_project_slug, GCP, DUASignature, DataAccess,
    ProjectSection)
from project.utility import readable_size
from project.validators import MAX_PROJECT_SLUG_LENGTH
from project.views import (get_file_forms, get_project_file_info,
    process_files_post)
from user.models import User, CredentialApplication, LegacyCredential
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

    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()

    passphrase = ''
    anonymous_url = project.get_anonymous_url()

    if 'generate_passphrase' in request.POST:
        anonymous_url, passphrase = project.generate_anonymous_access()
    elif 'remove_passphrase' in request.POST:
        project.anonymous.all().delete()
        anonymous_url, passphrase = '', 'revoked'

    url_prefix = notification.get_url_prefix(request)
    return render(request, 'console/submission_info.html',
        {'project': project, 'authors': authors,
         'author_emails': author_emails, 'storage_info': storage_info,
         'edit_logs': edit_logs, 'copyedit_logs': copyedit_logs,
         'latest_version': latest_version, 'passphrase': passphrase,
         'anonymous_url': anonymous_url, 'url_prefix': url_prefix,
         'project_info_nav': True})


@handling_editor
def edit_submission(request, project_slug, *args, **kwargs):
    """
    Page to respond to a particular submission, as an editor
    """
    project = kwargs['project']
    edit_log = project.edit_logs.get(decision_datetime__isnull=True)

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
         'editor_home': True})


@handling_editor
def copyedit_submission(request, project_slug, *args, **kwargs):
    """
    Page to copyedit the submission
    """
    project = kwargs['project']
    if project.submission_status != 40:
        return redirect('editor_home')

    copyedit_log = project.copyedit_logs.get(complete_datetime=None)

    # If form was submitted then define data
    # variable used to initialize the forms
    data_edit = request.POST if 'edit_content' in request.POST else None
    data_complete = request.POST if 'complete_copyedit' in request.POST else None

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

    description_form = project_forms.ContentForm(data=data_edit,
        resource_type=project.resource_type.id, instance=project)
    access_form = project_forms.AccessMetadataForm(instance=project, data=data_edit)
    access_form.set_license_queryset(access_policy=project.access_policy)
    discovery_form = project_forms.DiscoveryForm(resource_type=project.resource_type.id,
        instance=project, data=data_edit)

    reference_formset = ReferenceFormSet(instance=project, data=data_edit)
    publication_formset = PublicationFormSet(instance=project, data=data_edit)
    topic_formset = TopicFormSet(instance=project, data=data_edit)

    copyedit_form = forms.CopyeditForm(instance=copyedit_log, data=data_complete)

    # Creates forms for each section of this project
    # according to its content type
    valid = True
    section_forms = []
    sections = ProjectSection.objects.filter(resource_type=project.resource_type).order_by('default_order')
    for s in sections:
        form = project_forms.SectionContentForm(project=project, 
            project_section=s, data=data_edit)
        section_forms.append(form)
        # Validation of all `section_content` forms
        valid = valid and form.is_valid()

    if request.method == 'POST':
        if 'edit_content' in request.POST:
            if (description_form.is_valid() and access_form.is_valid()
                    and reference_formset.is_valid()
                    and publication_formset.is_valid()
                    and topic_formset.is_valid()
                    and discovery_form.is_valid()
                    and valid):

                description_form.save()
                access_form.save()
                discovery_form.save()
                reference_formset.save()
                publication_formset.save()
                topic_formset.save()
                for sf in section_forms:
                    sf.save()
                messages.success(request,
                    'The project metadata has been updated.')
            else:
                messages.error(request,
                    'Invalid submission. See errors below.')
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
        'section_forms':section_forms})


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
         'yesterday': yesterday, 'editor_home': True})


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
                utility.update_doi(published_project.core_project.doi,
                                   payload_core)

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
         'max_slug_length': MAX_PROJECT_SLUG_LENGTH, 'editor_home': True,
         'url_prefix': url_prefix})


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
    doi_form = forms.DOIForm(instance=project)
    topic_form = forms.TopicForm(project=project)
    topic_form.set_initial()
    deprecate_form = None if project.deprecated_files else forms.DeprecateFilesForm()
    has_credentials = os.path.exists(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    data_access_form = forms.DataAccessForm(project=project)
    if request.method == 'POST':
        if 'set_doi' in request.POST:
            doi_form = forms.DOIForm(data=request.POST, instance=project)
            if doi_form.is_valid():
                doi_form.save()
                messages.success(request, 'The DOI has been set')
            else:
                messages.error(request, 'Invalid submission. See form below.')
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
            else:
                make_checksum_background(
                    pid=project.id,
                    verbose_name='Making checksum file - {}'.format(project))
                messages.success(
                    request, 'The files checksum list has been scheduled.')
        elif 'make_zip' in request.POST:
            if any(get_associated_tasks(project)):
                messages.error(request, 'Project has tasks pending.')
            else:
                make_zip_background(
                    pid=project.id,
                    verbose_name='Making zip file - {}'.format(project))
                messages.success(
                    request, 'The zip of the main files has been scheduled.')
        elif 'deprecate_files' in request.POST and not project.deprecated_files:
            deprecate_form = forms.DeprecateFilesForm(data=request.POST)
            if deprecate_form.is_valid():
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
         'published': True, 'doi_form': doi_form, 'topic_form': topic_form,
         'deprecate_form': deprecate_form, 'has_credentials': has_credentials, 
         'data_access_form': data_access_form, 'data_access': data_access,
         'rw_tasks': rw_tasks, 'ro_tasks': ro_tasks,
         'anonymous_url': anonymous_url, 'passphrase': passphrase,
         'published_projects_nav': True, 'url_prefix': url_prefix})

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
def credential_applications(request):
    """
    Ongoing credential applications
    """
    applications = CredentialApplication.objects.filter(status=0)
    # Set first_date as the first occurrence of the following three
    applications = applications.annotate(first_date=functions.Coalesce(
            'reference_response_datetime', 'reference_contact_datetime',
            'application_datetime'))
    # Do the propper sort
    applications = applications.order_by(F('reference_contact_datetime').asc(
        nulls_first=True), 'application_datetime')
    # Set the days that have passed since the last action was taken
    for application in applications:
        application.time_elapsed = (timezone.now() - application.first_date).days

    return render(request, 'console/credential_applications.html',
        {'applications': applications, 'credentials_nav': True})

@login_required
@user_passes_test(is_admin, redirect_field_name='project_home')
def complete_credential_applications(request):
    """
    Ongoing credential applications
    """
    process_credential_form = forms.ProcessCredentialForm(responder=request.user)

    if request.method == 'POST':
        if 'contact_reference' in request.POST and request.POST['contact_reference'].isdigit():
            application_id = request.POST.get('contact_reference', '')
            application = CredentialApplication.objects.get(id=application_id)
            application.reference_contact_datetime = timezone.now()
            application.save()
            # notification.contact_reference(request, application)
            if application.reference_category == 0:
                mailto = notification.mailto_supervisor(request, application)
            else:
                mailto = notification.mailto_reference(request, application)
            # messages.success(request, 'The reference contact email has been created.')
            return render(request, 'console/generate_reference_email.html',
                {'application': application, 'mailto': mailto})
        if 'process_application' in request.POST and request.POST['process_application'].isdigit():
            application_id = request.POST.get('process_application', '')
            try:
                application = CredentialApplication.objects.get(id=application_id,
                    status=0)
            except CredentialApplication.DoesNotExist:
                messages.error(request, """The application has already been
                    processed. It may have been withdrawn by the applicant or
                    handled by another administrator.""")
                return redirect('complete_credential_applications')
            process_credential_form = forms.ProcessCredentialForm(
                responder=request.user, data=request.POST, instance=application)

            if process_credential_form.is_valid():
                application = process_credential_form.save()
                notification.process_credential_complete(request, application, comments=False)
                mailto = notification.mailto_process_credential_complete(
                    request, application)
                return render(request, 'console/generate_response_email.html',
                    {'application' : application, 'mailto': mailto})
            else:
                messages.error(request, 'Invalid submission. See form below.')

    applications = CredentialApplication.objects.filter(status=0)
    # Do the proper sort
    applications = applications.order_by(F('reference_contact_datetime').asc(
        nulls_first=True), 'application_datetime')

    for application in applications:
        application.mailto = notification.mailto_process_credential_complete(
            request, application, comments=False)
        if CredentialApplication.objects.filter(reference_email__iexact=application.reference_email,
            reference_contact_datetime__isnull=False).exclude(reference_email=''):
            # If the reference has been contacted before, mark it so
            application.known_ref = True
        elif LegacyCredential.objects.filter(reference_email__iexact=application.reference_email).exclude(
            reference_email=''):
            application.known_ref = True

    return render(request, 'console/complete_credential_applications.html',
        {'process_credential_form': process_credential_form, 
        'applications': applications, 'complete_credentials_nav': True})

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
    Process a credential application. View details, contact reference,
    and make final decision.
    """
    try:
        application = CredentialApplication.objects.get(slug=application_slug,
            status=0)
    except CredentialApplication.DoesNotExist:
        messages.error(request, """The application has already been
            processed. It may have been withdrawn by the applicant or
            handled by another administrator.""")
        return redirect('credential_applications')

    process_credential_form = forms.ProcessCredentialForm(responder=request.user,
        instance=application)

    if request.method == 'POST':
        if 'contact_reference' in request.POST:
            application.reference_contact_datetime = timezone.now()
            application.save()
            notification.contact_reference(request, application)
            messages.success(request, 'The reference has been contacted.')
        elif 'process_application' in request.POST:
            process_credential_form = forms.ProcessCredentialForm(
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
         'process_credential_form': process_credential_form,
         'credentials_nav': True})


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
                    c_application.user.is_credentialed = False
                    c_application.user.credential_datetime = None
                    c_application.decision_datetime = None
                    c_application.status = 1
                    dua_list = DUASignature.objects.filter(user = c_application.user,
                        project__access_policy = 2)
                    try:
                        with transaction.atomic():
                            for dua in dua_list:
                                dua.delete()
                            c_application.user.save()
                            c_application.save()
                    except DatabaseError:
                        messages.error(request, 'There was a database error. Please try again.')
            else:
                l_application = LegacyCredential.objects.filter(email=request.POST['remove_credentialing'])
                if l_application:
                    l_application = l_application.get()
                    l_application.migrated_user.credential_datetime = None
                    l_application.migrated_user.is_credentialed = False
                    l_application.migrated_user.save()
        elif 'manage_credentialing' in request.POST and request.POST['manage_credentialing'].isdigit():
            cid = request.POST['manage_credentialing']
            c_application = CredentialApplication.objects.filter(id=cid)
            if c_application:
                c_application = c_application.get()
                c_application.status = 0
                c_application.save()
        elif "search" in request.POST:
            all_successful_apps, unsuccessful_apps = search_credential_applications(request)
            if status == 'successful':
                return render(request, 'console/past_credential_successful_user_list.html',
                    {'applications': all_successful_apps,
                     'u_applications': unsuccessful_apps})
            elif status == 'unsuccessful':
                return render(request, 'console/past_credential_unsuccessful_user_list.html',
                    {'applications': all_successful_apps,
                     'u_applications': unsuccessful_apps})

    legacy_apps = LegacyCredential.objects.filter(migrated=True,
        migrated_user__is_credentialed=True).order_by('-migration_date')

    successful_apps = CredentialApplication.objects.filter(status=2
        ).order_by('-decision_datetime')
    unsuccessful_apps = CredentialApplication.objects.filter(status__in=[1, 3]
        ).order_by('-decision_datetime')

    # Merge legacy applications and new applications
    all_successful_apps = list(chain(successful_apps, legacy_apps))

    all_successful_apps = paginate(request, all_successful_apps, 50)
    unsuccessful_apps = paginate(request, unsuccessful_apps, 50)

    return render(request, 'console/past_credential_applications.html',
        {'applications': all_successful_apps, 'past_credentials_nav': True,
         'u_applications': unsuccessful_apps})


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

        # Merge legacy applications with new applications
        all_successful_apps = list(chain(successful_apps, legacy_apps))

        if len(search_field) == 0:
            all_successful_apps = paginate(request, all_successful_apps, 50)
            unsuccessful_apps = paginate(request, unsuccessful_apps, 50)

        return all_successful_apps, unsuccessful_apps


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

