import csv
import logging
import os
from collections import OrderedDict
from datetime import datetime
from itertools import chain
from statistics import StatisticsError, median

import notification.utility as notification
from background_task import background
from console.tasks import associated_task, get_associated_tasks
from dal import autocomplete
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.contrib.auth.models import Group
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.contrib.contenttypes.models import ContentType
from django.contrib.redirects.models import Redirect
from django.db.models import Count, DurationField, F, Q
from django.db.models.functions import Cast
from django.forms import Select, Textarea, modelformset_factory
from django.forms.models import model_to_dict
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from events.forms import EventAgreementForm, EventDatasetForm
from events.models import Event, EventAgreement, EventDataset, EventApplication
from notification.models import News
from physionet.forms import set_saved_fields_cookie
from physionet.middleware.maintenance import ServiceUnavailable
from physionet.utility import paginate
from physionet.models import FrontPageButton, Section, StaticPage
from project import forms as project_forms
from project.models import (
    GCP,
    GCPLog,
    AWS,
    AccessLog,
    AccessPolicy,
    ActiveProject,
    DataAccess,
    DUA,
    DataAccessRequest,
    DUASignature,
    EditLog,
    License,
    Publication,
    PublishedProject,
    Reference,
    StorageRequest,
    SubmissionStatus,
    Topic,
    exists_project_slug,
)
from project.authorization.access import can_view_project_files
from project.utility import readable_size
from project.validators import MAX_PROJECT_SLUG_LENGTH
from project.views import get_file_forms, get_project_file_info, process_files_post
from user.models import (
    AssociatedEmail,
    CredentialApplication,
    CredentialReview,
    LegacyCredential,
    User,
    Training,
    TrainingType,
    TrainingQuestion,
    CodeOfConduct,
    CloudInformation
)
from physionet.enums import LogCategory
from console import forms, utility, services
from console.forms import ProjectFilterForm, UserFilterForm
from project.cloud.s3 import (
    create_s3_bucket,
    upload_project_to_S3,
    get_bucket_name,
    check_s3_bucket_exists,
    update_bucket_policy,
    has_s3_credentials,
)

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


def handling_editor(base_view):
    """
    Access decorator. The user must be the editor of the project.
    """
    @login_required
    def handling_view(request, *args, **kwargs):
        user = request.user
        try:
            project = ActiveProject.objects.get(slug=kwargs['project_slug'])
            if user.has_access_to_admin_console() and user == project.editor:
                kwargs['project'] = project
                return base_view(request, *args, **kwargs)
        except ActiveProject.DoesNotExist:
            raise Http404()
        raise Http404('Unable to access page')
    return handling_view


def console_permission_required(perm):
    """
    Decorator for a view that requires user permissions.

    If the client is not logged in, or the user doesn't have the
    specified permission, the view raises PermissionDenied.

    The required permission name is also stored as an attribute for
    introspection purposes.
    """
    def wrapper(view):
        view = permission_required(perm, raise_exception=True)(view)
        view.required_permission = perm
        return view
    return wrapper


# ------------------------- Views begin ------------------------- #


@console_permission_required('user.can_view_admin_console')
def console_home(request):
    if not request.user.is_authenticated or not request.user.has_access_to_admin_console():
        raise PermissionDenied
    return render(request, 'console/console_home.html')


@console_permission_required('project.change_activeproject')
def submitted_projects(request):
    """
    List of active submissions. Editors are assigned here.
    """
    user = request.user
    if request.method == 'POST' and user.has_perm('project.can_assign_editor'):
        assign_editor_form = forms.AssignEditorForm(request.POST)
        if assign_editor_form.is_valid():
            # Move this into project method
            project = ActiveProject.objects.get(id=assign_editor_form.cleaned_data['project'])
            project.assign_editor(assign_editor_form.cleaned_data['editor'])
            notification.assign_editor_notify(project)
            notification.editor_notify_new_project(project, user)
            messages.success(request, 'The editor has been assigned')

    # Submitted projects
    projects = ActiveProject.objects.filter(submission_status__gt=SubmissionStatus.ARCHIVED).order_by(
        'submission_datetime')
    # Separate projects by submission status
    # Awaiting editor assignment
    assignment_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_ASSIGNMENT)
    # Awaiting editor decision
    decision_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_DECISION)
    # Awaiting author revisions
    revision_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_RESUBMISSION)
    # Awaiting editor copyedit
    copyedit_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_COPYEDIT)
    # Awaiting author approval
    approval_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_APPROVAL)
    # Awaiting editor publish
    publish_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_PUBLICATION)

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
                   'yesterday': yesterday})


@console_permission_required('project.change_activeproject')
def editor_home(request):
    """
    List of submissions the editor is responsible for
    """
    projects = ActiveProject.objects.filter(editor=request.user).order_by(
        'submission_datetime')

    # Awaiting editor decision
    decision_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_DECISION)
    # Awaiting author revisions
    revision_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_RESUBMISSION)
    # Awaiting editor copyedit
    copyedit_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_COPYEDIT)
    # Awaiting author approval
    approval_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_APPROVAL)
    # Awaiting editor publish
    publish_projects = projects.filter(submission_status=SubmissionStatus.NEEDS_PUBLICATION)

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


@console_permission_required('project.change_activeproject')
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
    embargo_form = forms.EmbargoFilesDaysForm()
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
    elif 'embargo_files' in request.POST:
        embargo_form = forms.EmbargoFilesDaysForm(data=request.POST)
        if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
            raise ServiceUnavailable()
        elif embargo_form.is_valid():
            days = embargo_form.cleaned_data['embargo_files_days']
            if days == 0:
                project.embargo_files_days = None
            else:
                project.embargo_files_days = days
            project.save()
            messages.success(request, f"An embargo was set for {project.embargo_files_days} day(s)")

    url_prefix = notification.get_url_prefix(request)
    bulk_url_prefix = notification.get_url_prefix(request, bulk_download=True)
    return render(request, 'console/submission_info.html',
                  {'project': project, 'authors': authors,
                   'author_emails': author_emails, 'storage_info': storage_info,
                   'edit_logs': edit_logs, 'copyedit_logs': copyedit_logs,
                   'latest_version': latest_version, 'passphrase': passphrase,
                   'anonymous_url': anonymous_url, 'url_prefix': url_prefix,
                   'bulk_url_prefix': bulk_url_prefix,
                   'reassign_editor_form': reassign_editor_form,
                   'embargo_form': embargo_form})


@handling_editor
def edit_submission(request, project_slug, *args, **kwargs):
    """
    Page to respond to a particular submission, as an editor
    """
    project = kwargs['project']

    try:
        edit_log = project.edit_logs.get(decision_datetime__isnull=True)
    except EditLog.DoesNotExist:
        return redirect('editor_home')

    reassign_editor_form = forms.ReassignEditorForm(request.user)
    embargo_form = forms.EmbargoFilesDaysForm()

    # The user must be the editor
    if project.submission_status not in [SubmissionStatus.NEEDS_DECISION, SubmissionStatus.NEEDS_RESUBMISSION]:
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
                project = ActiveProject.objects.get(slug=project_slug,
                                                    submission_status=SubmissionStatus.ARCHIVED)
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
    bulk_url_prefix = notification.get_url_prefix(request, bulk_download=True)

    return render(request, 'console/edit_submission.html',
                  {'project': project, 'edit_submission_form': edit_submission_form,
                   'authors': authors, 'author_emails': author_emails,
                   'storage_info': storage_info, 'edit_logs': edit_logs,
                   'latest_version': latest_version, 'url_prefix': url_prefix,
                   'bulk_url_prefix': bulk_url_prefix,
                   'editor_home': True, 'reassign_editor_form': reassign_editor_form,
                   'embargo_form': embargo_form})


@handling_editor
def copyedit_submission(request, project_slug, *args, **kwargs):
    """
    Page to copyedit the submission
    """
    project = kwargs['project']
    if project.submission_status != SubmissionStatus.NEEDS_COPYEDIT:
        return redirect('editor_home')

    copyedit_log = project.copyedit_logs.get(complete_datetime=None)
    reassign_editor_form = forms.ReassignEditorForm(request.user)
    embargo_form = forms.EmbargoFilesDaysForm()

    # Metadata forms and formsets
    ReferenceFormSet = generic_inlineformset_factory(Reference,
                                                     fields=('description',), extra=0,
                                                     max_num=project_forms.ReferenceFormSet.max_forms,
                                                     can_delete=False,
                                                     formset=project_forms.ReferenceFormSet, validate_max=True)
    TopicFormSet = generic_inlineformset_factory(Topic,
                                                 fields=('description',), extra=0,
                                                 max_num=project_forms.TopicFormSet.max_forms,
                                                 can_delete=False,
                                                 formset=project_forms.TopicFormSet, validate_max=True)
    PublicationFormSet = generic_inlineformset_factory(Publication,
                                                       fields=('citation', 'url'), extra=0,
                                                       max_num=project_forms.PublicationFormSet.max_forms,
                                                       can_delete=False,
                                                       formset=project_forms.PublicationFormSet, validate_max=True)

    description_form = project_forms.ContentForm(
        resource_type=project.resource_type.id, instance=project)
    ethics_form = project_forms.EthicsForm(instance=project)

    access_policy = request.GET.get('accessPolicy')
    if access_policy:
        access_form = project_forms.AccessMetadataForm(instance=project, access_policy=int(access_policy))
    else:
        access_form = project_forms.AccessMetadataForm(instance=project)

    discovery_form = project_forms.DiscoveryForm(resource_type=project.resource_type.id,
                                                 instance=project)
    description_form_saved = False
    reference_formset = ReferenceFormSet(instance=project)
    publication_formset = PublicationFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    copyedit_form = forms.CopyeditForm(instance=copyedit_log)

    if request.method == 'POST':
        if 'edit_content' in request.POST:
            description_form = project_forms.ContentForm(
                resource_type=project.resource_type.id, data=request.POST,
                instance=project)
            ethics_form = project_forms.EthicsForm(data=request.POST, instance=project)
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
            if (
                description_form.is_valid()
                and access_form.is_valid()
                and ethics_form.is_valid()
                and reference_formset.is_valid()
                and publication_formset.is_valid()
                and topic_formset.is_valid()
                and discovery_form.is_valid()
            ):
                description_form.save()
                ethics_form.save()
                access_form.save()
                discovery_form.save()
                reference_formset.save()
                publication_formset.save()
                topic_formset.save()
                messages.success(request,
                                 'The project metadata has been updated.')
                description_form_saved = True
                # Reload formsets
                reference_formset = ReferenceFormSet(instance=project)
                publication_formset = PublicationFormSet(instance=project)
                topic_formset = TopicFormSet(instance=project)
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

    (
        authors,
        author_emails,
        storage_info,
        edit_logs,
        copyedit_logs,
        latest_version,
    ) = project.info_card(force_calculate=True)

    (
        display_files,
        display_dirs,
        dir_breadcrumbs,
        _,
        file_error
    ) = get_project_file_info(project=project, subdir=subdir)

    (upload_files_form, create_folder_form, rename_item_form,
     move_items_form, delete_items_form) = get_file_forms(
         project=project, subdir=subdir, display_dirs=display_dirs)

    edit_url = reverse('edit_content_item', args=[project.slug])
    url_prefix = notification.get_url_prefix(request)
    bulk_url_prefix = notification.get_url_prefix(request)

    response = render(
        request,
        'console/copyedit_submission.html',
        {
            'project': project,
            'description_form': description_form,
            'ethics_form': ethics_form,
            'individual_size_limit': readable_size(ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT),
            'access_form': access_form,
            'reference_formset': reference_formset,
            'publication_formset': publication_formset,
            'topic_formset': topic_formset,
            'storage_type': settings.STORAGE_TYPE,
            'storage_info': storage_info,
            'upload_files_form': upload_files_form,
            'create_folder_form': create_folder_form,
            'rename_item_form': rename_item_form,
            'move_items_form': move_items_form,
            'delete_items_form': delete_items_form,
            'subdir': subdir,
            'display_files': display_files,
            'display_dirs': display_dirs,
            'dir_breadcrumbs': dir_breadcrumbs,
            'file_error': file_error,
            'editor_home': True,
            'is_editor': True,
            'files_editable': True,
            'copyedit_form': copyedit_form,
            'authors': authors,
            'author_emails': author_emails,
            'edit_logs': edit_logs,
            'copyedit_logs': copyedit_logs,
            'latest_version': latest_version,
            'add_item_url': edit_url,
            'remove_item_url': edit_url,
            'discovery_form': discovery_form,
            'url_prefix': url_prefix,
            'bulk_url_prefix': bulk_url_prefix,
            'reassign_editor_form': reassign_editor_form,
            'embargo_form': embargo_form,
        },
    )
    if description_form_saved:
        set_saved_fields_cookie(description_form, request.path, response)
    return response


@handling_editor
def awaiting_authors(request, project_slug, *args, **kwargs):
    """
    View the authors who have and have not approved the project for
    publication.

    Also the page to reopen the project for copyediting.
    """
    project = kwargs['project']

    if project.submission_status != SubmissionStatus.NEEDS_APPROVAL:
        return redirect('editor_home')

    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()
    outstanding_emails = ';'.join([a.user.email for a in authors.filter(
        approval_datetime=None)])
    reassign_editor_form = forms.ReassignEditorForm(request.user)
    embargo_form = forms.EmbargoFilesDaysForm()

    if request.method == 'POST':
        if 'reopen_copyedit' in request.POST:
            project.reopen_copyedit()
            notification.reopen_copyedit_notify(request, project)
            return render(request, 'console/reopen_copyedit_complete.html',
                          {'project': project})
        elif 'send_reminder' in request.POST:
            notification.copyedit_complete_notify(request, project,
                                                  project.copyedit_logs.last(), reminder=True)
            messages.success(request, 'The reminder email has been sent.')
            project.latest_reminder = timezone.now()
            project.save()

    url_prefix = notification.get_url_prefix(request)
    bulk_url_prefix = notification.get_url_prefix(request, bulk_download=True)
    yesterday = timezone.now() + timezone.timedelta(days=-1)

    return render(request, 'console/awaiting_authors.html',
                  {'project': project, 'authors': authors, 'author_emails': author_emails,
                   'storage_info': storage_info, 'edit_logs': edit_logs,
                   'copyedit_logs': copyedit_logs, 'latest_version': latest_version,
                   'outstanding_emails': outstanding_emails, 'url_prefix': url_prefix,
                   'bulk_url_prefix': bulk_url_prefix,
                   'yesterday': yesterday, 'editor_home': True,
                   'reassign_editor_form': reassign_editor_form,
                   'embargo_form': embargo_form})


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

    return JsonResponse({'available': result})


@handling_editor
def publish_submission(request, project_slug, *args, **kwargs):
    """
    Page to publish the submission
    """
    project = kwargs['project']

    if project.submission_status != SubmissionStatus.NEEDS_PUBLICATION:
        return redirect('editor_home')
    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        raise ServiceUnavailable()

    reassign_editor_form = forms.ReassignEditorForm(request.user)
    embargo_form = forms.EmbargoFilesDaysForm()
    authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version = project.info_card()
    if request.method == 'POST':
        publish_form = forms.PublishForm(project=project, data=request.POST)
        if project.is_publishable() and publish_form.is_valid():
            if project.is_new_version:
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

            return render(
                request,
                'console/publish_complete.html',
                {'published_project': published_project, 'editor_home': True},
            )

    publishable = project.is_publishable()
    url_prefix = notification.get_url_prefix(request)
    bulk_url_prefix = notification.get_url_prefix(request, bulk_download=True)
    publish_form = forms.PublishForm(project=project)

    return render(request, 'console/publish_submission.html',
                  {'project': project, 'publishable': publishable, 'authors': authors,
                   'author_emails': author_emails, 'storage_info': storage_info,
                   'edit_logs': edit_logs, 'copyedit_logs': copyedit_logs,
                   'latest_version': latest_version, 'publish_form': publish_form,
                   'max_slug_length': MAX_PROJECT_SLUG_LENGTH, 'url_prefix': url_prefix,
                   'bulk_url_prefix': bulk_url_prefix,
                   'reassign_editor_form': reassign_editor_form, 'editor_home': True,
                   'embargo_form': embargo_form})


@console_permission_required('project.change_storagerequest')
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
                                 (f"The storage request has been "
                                  f"{notification.RESPONSE_ACTIONS[storage_request.response]}"))


@console_permission_required('project.change_storagerequest')
def storage_requests(request):
    """
    Page for listing and responding to project storage requests
    """
    StorageResponseFormSet = modelformset_factory(StorageRequest,
                                                  fields=('response', 'response_message'),
                                                  widgets={'response': Select(choices=forms.RESPONSE_CHOICES),
                                                           'response_message': Textarea()}, extra=0)

    if request.method == 'POST':
        storage_response_formset = StorageResponseFormSet(request.POST,
                                                          queryset=StorageRequest.objects.filter(is_active=True))
        process_storage_response(request, storage_response_formset)

    storage_response_formset = StorageResponseFormSet(
        queryset=StorageRequest.objects.filter(is_active=True))

    return render(request, 'console/storage_requests.html',
                  {'storage_response_formset': storage_response_formset})


@console_permission_required('project.change_activeproject')
def unsubmitted_projects(request):
    """
    List of unsubmitted projects
    """
    projects = ActiveProject.objects.filter(submission_status=SubmissionStatus.UNSUBMITTED).order_by(
        'creation_datetime')
    projects = paginate(request, projects, 50)
    return render(request, 'console/unsubmitted_projects.html',
                  {'projects': projects})


@console_permission_required('project.change_publishedproject')
def published_projects(request):
    """
    List of published projects
    """
    projects = PublishedProject.objects.all().order_by('-publish_datetime')
    projects = paginate(request, projects, 50)
    return render(request, 'console/published_projects.html',
                  {'projects': projects})


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


@associated_task(PublishedProject, "pid", read_only=True)
@background()
def send_files_to_aws(pid):
    """
    Upload project files to AWS S3 buckets.

    This function retrieves the project identified by 'pid' and uploads
    its files to the appropriate AWS S3 bucket. It utilizes the
    'upload_project_to_S3' function from the 'utility' module.

    Args:
        pid (int): The unique identifier (ID) of the project to upload.

    Returns:
        None

    Note:
    - Verify that AWS credentials and configurations are correctly set
    up for the S3 client.
    """
    project = PublishedProject.objects.get(id=pid)
    upload_project_to_S3(project)
    project.aws.sent_files = True
    project.aws.finished_datetime = timezone.now()
    if project.compressed_storage_size:
        project.aws.sent_zip = True
    project.aws.save()


@associated_task(PublishedProject, "pid", read_only=True)
@background()
def update_aws_bucket_policy(pid):
    """
    Update the AWS S3 bucket's access policy based on the
    project's access policy.

    This function determines the access policy of the project identified
    by 'pid' and updates the AWS S3 bucket's access policy accordingly.
    It checks if the bucket exists, retrieves its name, and uses the
    'utility.update_bucket_policy' function for the update.

    Args:
        pid (int): The unique identifier (ID) of the project for which to
        update the bucket policy.

    Returns:
        bool: True if the bucket policy was updated successfully,
        False otherwise.

    Note:
    - Verify that AWS credentials and configurations are correctly set up
    for the S3 client.
    - The 'updated_policy' variable indicates whether the policy was
    updated successfully.
    """
    updated_policy = False
    project = PublishedProject.objects.get(id=pid)
    exists = check_s3_bucket_exists(project)
    if exists:
        bucket_name = get_bucket_name(project)
        update_bucket_policy(project, bucket_name)
        updated_policy = True
    else:
        updated_policy = False
    return updated_policy


@console_permission_required('project.change_publishedproject')
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


@console_permission_required('project.change_publishedproject')
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
    has_credentials = bool(settings.GOOGLE_APPLICATION_CREDENTIALS)
    data_access_form = forms.DataAccessForm(project=project)
    contact_form = forms.PublishedProjectContactForm(project=project,
                                                     instance=project.contact)
    legacy_author_form = forms.CreateLegacyAuthorForm(project=project)
    publication_form = forms.AddPublishedPublicationForm(project=project)

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
        elif 'remove_embargo' in request.POST:
            if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
                raise ServiceUnavailable()
            else:
                project.embargo_files_days = None
                project.save()
                messages.success(request, 'The project files are no longer under embargo.')
        elif 'bucket' in request.POST and has_credentials:
            if any(get_associated_tasks(project, read_only=False)):
                messages.error(request, 'Project has tasks pending.')
            else:
                gcp_bucket_management(request, project, user)
        elif 'aws-bucket' in request.POST and has_s3_credentials():
            if any(get_associated_tasks(project, read_only=False)):
                messages.error(request, 'Project has tasks pending.')
            else:
                aws_bucket_management(request, project, user)
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
        elif 'set_publication' in request.POST:
            publication_form = forms.AddPublishedPublicationForm(
                project=project, data=request.POST)
            if publication_form.is_valid():
                publication_form.save()
                messages.success(request, 'The associated publication has been added')
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
    bulk_url_prefix = notification.get_url_prefix(request)

    return render(
        request,
        'console/manage_published_project.html',
        {
            'project': project,
            'authors': authors,
            'author_emails': author_emails,
            'storage_info': storage_info,
            'edit_logs': edit_logs,
            'copyedit_logs': copyedit_logs,
            'latest_version': latest_version,
            'published': True,
            'topic_form': topic_form,
            'deprecate_form': deprecate_form,
            'has_credentials': has_credentials,
            'has_s3_credentials': has_s3_credentials(),
            # 'aws_bucket_exists': s3_bucket_exists,
            # 's3_bucket_name': s3_bucket_name,
            'data_access_form': data_access_form,
            'data_access': data_access,
            'rw_tasks': rw_tasks,
            'ro_tasks': ro_tasks,
            'anonymous_url': anonymous_url,
            'passphrase': passphrase,
            'url_prefix': url_prefix,
            'bulk_url_prefix': bulk_url_prefix,
            'contact_form': contact_form,
            'legacy_author_form': legacy_author_form,
            'publication_form': publication_form,
            'can_make_zip': project.files.can_make_zip(),
            'can_make_checksum': project.files.can_make_checksum(),
        },
    )


@console_permission_required('project.change_publishedproject')
def gcp_bucket_management(request, project, user):
    """
    Create the database object and cloud bucket if they do not exist, and send
    the files to the bucket.
    """
    is_private = True

    if project.access_policy == AccessPolicy.OPEN:
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


@console_permission_required('project.change_publishedproject')
def aws_bucket_management(request, project, user):
    """
    Manage AWS S3 bucket for a project.

    This function is responsible for sending the project's files
    to that bucket. It orchestrates the necessary steps to set up
    the bucket and populate it with the project's data.

    Args:
        project (PublishedProject): The project for which to create and
        populate the AWS S3 bucket.

    Returns:
        None

    Note:
    - Ensure that AWS credentials and configurations are correctly set
    up for the S3 client.
    """
    is_private = True

    if project.access_policy == AccessPolicy.OPEN:
        is_private = False

    bucket_name = get_bucket_name(project)

    if not AWS.objects.filter(project=project).exists():
        AWS.objects.create(
            project=project, bucket_name=bucket_name, is_private=is_private
        )

    send_files_to_aws(project.id, verbose_name='AWS - {}'.format(project), creator=user)


@console_permission_required('project.change_publishedproject')
def cloud_mirrors(request):
    """
    Page for viewing the status of cloud mirrors.
    """
    projects = PublishedProject.objects.order_by('-publish_datetime')

    group = request.GET.get('group', 'open')
    if group == 'open':
        projects = projects.filter(access_policy=AccessPolicy.OPEN)
    else:
        projects = projects.exclude(access_policy=AccessPolicy.OPEN)

    cloud_platforms = []
    if settings.GOOGLE_APPLICATION_CREDENTIALS:
        cloud_platforms.append({
            'field_name': 'gcp',
            'name': 'GCP',
            'long_name': 'Google Cloud Platform',
        })
    if has_s3_credentials():
        cloud_platforms.append({
            'field_name': 'aws',
            'name': 'AWS',
            'long_name': 'Amazon Web Services',
        })

    # Relevant fields for the status table (see
    # templates/console/cloud_mirrors.html)
    field_names = [platform['field_name'] for platform in cloud_platforms]
    projects = projects.select_related(*field_names).only(
        'slug',
        'title',
        'version',
        'access_policy',
        'allow_file_downloads',
        'deprecated_files',
        'embargo_files_days',
        *(f'{field}__is_private' for field in field_names),
        *(f'{field}__sent_files' for field in field_names),
    )

    project_mirrors = {
        project: [
            getattr(project, field, None) for field in field_names
        ] for project in projects
    }

    return render(request, 'console/cloud_mirrors.html', {
        'group': group,
        'cloud_platforms': cloud_platforms,
        'project_mirrors': project_mirrors,
    })


@console_permission_required('project.change_activeproject')
def archived_submissions(request):
    """
    List of archived submissions
    """
    projects = ActiveProject.objects.filter(submission_status=SubmissionStatus.ARCHIVED
                                            ).order_by('creation_datetime')
    projects = paginate(request, projects, 50)
    return render(request, 'console/archived_submissions.html',
                  {'projects': projects})


@console_permission_required('user.view_user')
def users(request, group='all'):
    """
    List of users
    """
    user_list = User.objects.select_related('profile').annotate(
        login_time_count=Count('login_time')
    ).order_by('username')
    if group == 'admin':
        admin_users = user_list.filter(groups__name='Admin')
        return render(request, 'console/users_admin.html', {
            'admin_users': admin_users,
            'group': group,
        })
    elif group == 'active':
        user_list = user_list.filter(is_active=True)
    elif group == 'inactive':
        user_list = user_list.filter(is_active=False)

    users = paginate(request, user_list, 50)

    return render(request, 'console/users.html', {'users': users, 'group': group})


@console_permission_required('user.view_user')
def user_groups(request):
    """
    List of all user groups
    """
    groups = Group.objects.all().order_by('name')
    for group in groups:
        group.user_count = User.objects.filter(groups=group).count()
    return render(request, 'console/user_groups.html', {'groups': groups})


@console_permission_required('user.view_user')
def user_group(request, group):
    """
    Shows details of a user group, lists users in the group, lists permissions for the group
    """
    group = get_object_or_404(Group, name=group)
    users = User.objects.filter(groups=group).order_by('username').annotate(login_time_count=Count('login_time'))
    permissions = group.permissions.all().order_by('content_type__app_label', 'content_type__model')
    return render(
        request,
        'console/user_group.html',
        {'group': group, 'users': users, 'permissions': permissions}
    )


@console_permission_required('user.view_user')
def user_management(request, username):
    """
    Admin page for managing an individual user account.
    """
    user = get_object_or_404(User, username__iexact=username)
    try:
        aws_info = CloudInformation.objects.get(user=user).aws_id
    except CloudInformation.DoesNotExist:
        aws_info = None
    try:
        gcp_info = CloudInformation.objects.get(user=user).gcp_email
    except CloudInformation.DoesNotExist:
        gcp_info = None

    _training = Training.objects.select_related('training_type').filter(user=user).order_by('-status')

    training = {}
    training['Active'] = _training.get_valid()
    training['Under review'] = _training.get_review()
    training['Expired'] = _training.get_expired()
    training['Rejected'] = _training.get_rejected()

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
    projects["Unsubmitted"] = ActiveProject.objects.filter(
        authors__user=user, submission_status=SubmissionStatus.UNSUBMITTED
    ).order_by("-creation_datetime")
    projects["Submitted"] = ActiveProject.objects.filter(
        authors__user=user, submission_status__gt=SubmissionStatus.ARCHIVED
    ).order_by("-submission_datetime")
    projects['Archived'] = ActiveProject.objects.filter(authors__user=user,
                                                        submission_status=SubmissionStatus.ARCHIVED
                                                        ).order_by('-creation_datetime')
    projects['Published'] = PublishedProject.objects.filter(authors__user=user).order_by('-publish_datetime')

    credentialing_app = CredentialApplication.objects.filter(user=user).order_by("application_datetime")

    groups = user.groups.all()

    return render(request, 'console/user_management.html', {'subject': user,
                                                            'profile': user.profile,
                                                            'groups': groups,
                                                            'emails': emails,
                                                            'projects': projects,
                                                            'training_list': training,
                                                            'credentialing_app': credentialing_app,
                                                            'aws_info': aws_info,
                                                            'gcp_info': gcp_info})


@console_permission_required('user.view_user')
def users_search(request, group):
    """
    Search user list.

    Args:
        group (str): group of users to filter search. Either 'all' for all users or
            'inactive' to filter to inactive users only.
    """

    if request.method == 'POST':
        search_field = request.POST['search']

        users = User.objects.filter(Q(username__icontains=search_field)
                                    | Q(profile__first_names__icontains=search_field)
                                    | Q(profile__last_name__icontains=search_field)
                                    | Q(email__icontains=search_field)
                                    | Q(associated_emails__email__icontains=search_field)
                                    ).distinct()

        if 'inactive' in group:
            users = users.filter(is_active=False)
        elif 'active' in group:
            users = users.filter(is_active=True)

        users = users.order_by('username')

        if len(search_field) == 0:
            users = paginate(request, users, 50)

        return render(request, 'console/users_list.html', {'users': users,
                                                           'group': group})

    raise Http404()


@console_permission_required('user.change_credentialapplication')
def known_references_search(request):
    """
    Search credential applications and user list.
    """

    if request.method == 'POST':
        search_field = request.POST['search']

        applications = CredentialApplication.objects.filter(
            Q(reference_email__icontains=search_field)
            | Q(reference_name__icontains=search_field)
            | Q(user__profile__last_name__icontains=search_field)
            | Q(user__profile__first_names__icontains=search_field))

        all_known_ref = applications.exclude(
            reference_contact_datetime__isnull=True).order_by(
            '-reference_contact_datetime')

        if len(search_field) == 0:
            all_known_ref = paginate(request, all_known_ref, 50)

        return render(request, 'console/known_references_list.html', {
            'all_known_ref': all_known_ref})

    raise Http404()


@console_permission_required('user.change_credentialapplication')
def complete_credential_applications(request):
    """
    Legacy page for processing credentialing applications.
    """
    return redirect(credential_processing)


@console_permission_required('user.change_credentialapplication')
def complete_list_credentialed_people(request):
    """
    Legacy page that displayed a list of all approved MIMIC users.
    """
    return redirect(credential_applications, "successful")


@console_permission_required('user.change_credentialapplication')
def process_credential_application(request, application_slug):
    """
    Process a credential application. View details, advance to next stage,
    contact reference, and make final decision.
    """
    try:
        application = CredentialApplication.objects.get(
            slug=application_slug, status=CredentialApplication.Status.PENDING)
        # create the review object if it does not exist
        CredentialReview.objects.get_or_create(application=application)
    except CredentialApplication.DoesNotExist:
        messages.error(request, """The application has already been
            processed. It may have been withdrawn by the applicant or
            handled by another administrator.""")
        return redirect('credential_applications', status='pending')

    # get training list
    _training = Training.objects.select_related('training_type').filter(user=application.user).order_by('-status')
    training = {}
    training['Active'] = _training.get_valid()
    training['Under review'] = _training.get_review()
    training['Expired'] = _training.get_expired()
    training['Rejected'] = _training.get_rejected()

    ref_email = notification.contact_reference(request, application,
                                               send=False, wordwrap=False)
    contact_cred_ref_form = forms.ContactCredentialRefForm(initial=ref_email)

    page_title = None
    title_dict = {a: k for a, k in CredentialReview.REVIEW_STATUS_LABELS}
    page_title = title_dict[application.credential_review.status]

    credential_review_form = forms.CredentialReviewForm()

    if application.credential_review.status == 10:
        intermediate_credential_form = forms.PersonalCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 20:
        intermediate_credential_form = forms.ReferenceCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 30:
        intermediate_credential_form = forms.ResponseCredentialForm(responder=request.user, instance=application)
    if application.credential_review.status == 40:
        intermediate_credential_form = forms.ProcessCredentialReviewForm(responder=request.user, instance=application)

    if request.method == 'POST':
        if 'reject' in request.POST:
            credential_review_form = forms.CredentialReviewForm(data=request.POST)
            if credential_review_form.is_valid():
                application.responder_comments = credential_review_form.cleaned_data['reviewer_comments']
                application.save()
                application.reject(request.user)
                notification.process_credential_complete(request, application)
                messages.success(request, 'The application was not approved.')
                return redirect(credential_processing)
        # PROCESS ID STAGE
        elif 'accept_id' in request.POST:
            credential_review_form = forms.CredentialReviewForm(data=request.POST)
            if credential_review_form.is_valid():
                application.responder_comments = credential_review_form.cleaned_data['reviewer_comments']
                application.save()
            application.update_review_status(20)
            messages.success(request, 'The ID was approved.')
            page_title = title_dict[application.credential_review.status]
            # reset form
            credential_review_form = forms.CredentialReviewForm()
        elif 'full_approve' in request.POST:
            credential_review_form = forms.CredentialReviewForm(data=request.POST)
            if credential_review_form.is_valid():
                application.responder_comments = credential_review_form.cleaned_data['reviewer_comments']
                application.save()
            application.accept(responder=request.user)
            messages.success(request, 'The application has been accepted')
            notification.process_credential_complete(request, application)
            return redirect(credential_processing)
        # PROCESS REFERENCE CHECK STAGE
        elif 'accept_ref' in request.POST:
            contact_cred_ref_form = forms.ContactCredentialRefForm(data=request.POST)
            if contact_cred_ref_form.is_valid():
                application.update_review_status(30)
                application.reference_contact_datetime = timezone.now()
                application.save()
                subject = contact_cred_ref_form.cleaned_data['subject']
                body = contact_cred_ref_form.cleaned_data['body']
                notification.contact_reference(request, application,
                                               subject=subject, body=body)
                messages.success(request, 'The reference was contacted.')
                page_title = title_dict[application.credential_review.status]
                # reset form
                contact_cred_ref_form = forms.ContactCredentialRefForm(initial=ref_email)
        elif 'skip_ref' in request.POST:
            credential_review_form = forms.CredentialReviewForm(data=request.POST)
            if credential_review_form.is_valid():
                application.responder_comments = credential_review_form.cleaned_data['reviewer_comments']
                application.save()
            application.update_review_status(40)
            messages.success(request, 'The reference was skipped.')
            page_title = title_dict[application.credential_review.status]
            # reset form
            credential_review_form = forms.CredentialReviewForm()
        # CONTACT REFERENCE AGAIN
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
                messages.success(request, 'The reference was contacted.')
        # APPROVE THE RESPONSE FROM THE REFERENCE
        elif 'approve_response' in request.POST:
            intermediate_credential_form = forms.ResponseCredentialForm(
                responder=request.user, data=request.POST, instance=application)
            if intermediate_credential_form.is_valid():
                intermediate_credential_form.save()
                if intermediate_credential_form.cleaned_data['decision'] == '0':
                    notification.process_credential_complete(request,
                                                             application)
                    return render(request, 'console/process_credential_complete.html',
                                  {'application': application, 'CredentialApplication': CredentialApplication})
                page_title = title_dict[application.credential_review.status]
                intermediate_credential_form = forms.ProcessCredentialReviewForm(
                    responder=request.user, instance=application)
            else:
                messages.error(request, 'Invalid review. See form below.')
        # FINAL APPROVAL
        elif 'accept_final' in request.POST:
            credential_review_form = forms.CredentialReviewForm(data=request.POST)
            if credential_review_form.is_valid():
                application.responder_comments = credential_review_form.cleaned_data['reviewer_comments']
                application.save()
            application.accept(responder=request.user)
            notification.process_credential_complete(request, application)
            messages.success(request, 'The application was accepted')
            return redirect(credential_processing)
    return render(request, 'console/process_credential_application.html',
                  {'application': application, 'app_user': application.user,
                   'intermediate_credential_form': intermediate_credential_form,
                   'credential_review_form': credential_review_form,
                   'page_title': page_title,
                   'contact_cred_ref_form': contact_cred_ref_form,
                   'training_list': training})


@console_permission_required('user.change_credentialapplication')
def credential_processing(request):
    """
    Process applications for credentialed access.
    """
    applications = CredentialApplication.objects.filter(
        status=CredentialApplication.Status.PENDING).select_related('user__profile')

    # Allow filtering by event.
    if 'event' in request.GET:
        slug = request.GET['event']
        event = Event.objects.get(slug=slug)
        users = User.objects.filter(eventparticipant__event=event)
        applications = applications.filter(user__in=users)

    # Awaiting initial review
    initial_1 = Q(credential_review__isnull=True)
    initial_2 = Q(credential_review__status=10)
    personal_applications = applications.filter(
        initial_1 | initial_2).order_by('application_datetime')
    # Awaiting reference check
    reference_applications = applications.filter(credential_review__status=20).order_by('application_datetime')
    # Awaiting reference response
    response_applications = applications.filter(credential_review__status=30).order_by(
        '-reference_response', 'application_datetime'
    )
    # Awaiting final review
    final_applications = applications.filter(
        credential_review__status=40).order_by('application_datetime')

    if request.method == 'POST':
        if 'reset_application' in request.POST:
            try:
                application = CredentialApplication.objects.get(slug=request.POST['reset_application'])
            except CredentialApplication.DoesNotExist:
                raise Http404()
            application.credential_review.delete()
            messages.success(request, 'The application has been reset')

    return render(request, 'console/credential_processing.html',
                  {'applications': applications,
                   'personal_applications': personal_applications,
                   'reference_applications': reference_applications,
                   'response_applications': response_applications,
                   'final_applications': final_applications})


@console_permission_required('user.change_credentialapplication')
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
                   'form': form, 'CredentialApplication': CredentialApplication})


@console_permission_required('user.change_credentialapplication')
def credential_applications(request, status):
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
                c_application.status = CredentialApplication.Status.PENDING
                c_application.save()
        elif "search" in request.POST:
            (all_successful_apps, unsuccessful_apps,
                pending_apps) = search_credential_applications(request)
            if status == 'successful':
                return render(request, 'console/credential_successful_user_list.html',
                              {'applications': all_successful_apps,
                               'u_applications': unsuccessful_apps,
                               'p_applications': pending_apps})
            elif status == 'unsuccessful':
                return render(request, 'console/credential_unsuccessful_user_list.html',
                              {'applications': all_successful_apps,
                               'u_applications': unsuccessful_apps,
                               'p_applications': pending_apps})
            elif status == 'pending':
                return render(request, 'console/credential_pending_user_list.html',
                              {'applications': all_successful_apps,
                               'u_applications': unsuccessful_apps,
                               'p_applications': pending_apps})

    legacy_apps = (LegacyCredential.objects.filter(migrated=True,
                                                   migrated_user__is_credentialed=True)
                   .order_by('-migration_date')
                   .select_related('migrated_user__profile'))

    successful_apps = (CredentialApplication.objects.filter(
        status=CredentialApplication.Status.ACCEPTED).
                       order_by('-decision_datetime')
                       .select_related('user__profile', 'responder__profile'))

    unsuccessful_apps = CredentialApplication.objects.filter(
        status__in=[CredentialApplication.Status.REJECTED,
                    CredentialApplication.Status.WITHDRAWN,
                    CredentialApplication.Status.REVOKED]
    ).order_by('-decision_datetime').select_related('user__profile', 'responder')

    pending_apps = (CredentialApplication.objects.filter(
        status=CredentialApplication.Status.PENDING)
                    .order_by('-application_datetime')
                    .select_related('user__profile', 'credential_review'))

    # Merge legacy applications and new applications
    all_successful_apps = list(chain(successful_apps, legacy_apps))

    all_successful_apps = paginate(request, all_successful_apps, 50)
    unsuccessful_apps = paginate(request, unsuccessful_apps, 50)
    pending_apps = paginate(request, pending_apps, 50)

    return render(request, 'console/credential_applications.html',
                  {'applications': all_successful_apps,
                   'u_applications': unsuccessful_apps,
                   'p_applications': pending_apps})


@console_permission_required('user.change_credentialapplication')
def search_credential_applications(request):
    """
    Search past credentialing applications.

    Args:
        request (obj): Django WSGIRequest object.
    """
    if request.POST:
        search_field = request.POST['search']
        pending_status = CredentialApplication.Status.PENDING
        accepted_status = CredentialApplication.Status.ACCEPTED
        rejected_status = CredentialApplication.Status.REJECTED
        withdrawn_status = CredentialApplication.Status.WITHDRAWN

        legacy_apps = (LegacyCredential.objects.filter(
            Q(migrated=True)
            & Q(migrated_user__is_credentialed=True)
            & (Q(migrated_user__username__icontains=search_field)
               | Q(migrated_user__profile__first_names__icontains=search_field)
               | Q(migrated_user__profile__last_name__icontains=search_field)
               | Q(migrated_user__email__icontains=search_field))).order_by('-migration_date'))

        successful_apps = CredentialApplication.objects.filter(
            Q(status=accepted_status) & (Q(user__username__icontains=search_field)
                                         | Q(user__profile__first_names__icontains=search_field)
                           | Q(user__profile__last_name__icontains=search_field)
                           | Q(user__email__icontains=search_field))).order_by('-application_datetime')

        unsuccessful_apps = CredentialApplication.objects.filter(
            Q(status__in=[rejected_status, withdrawn_status])
            & (Q(user__username__icontains=search_field) | Q(user__profile__first_names__icontains=search_field)
                                    | Q(user__profile__last_name__icontains=search_field)
                                    | Q(user__email__icontains=search_field))).order_by('-application_datetime')

        pending_apps = CredentialApplication.objects.filter(
            Q(status=pending_status) & (Q(user__username__icontains=search_field)
                                        | Q(user__profile__first_names__icontains=search_field)
                           | Q(user__profile__last_name__icontains=search_field)
                           | Q(user__email__icontains=search_field))).order_by('-application_datetime')

        # Merge legacy applications with new applications
        all_successful_apps = list(chain(successful_apps, legacy_apps))

        if len(search_field) == 0:
            all_successful_apps = paginate(request, all_successful_apps, 50)
            unsuccessful_apps = paginate(request, unsuccessful_apps, 50)
            pending_apps = paginate(request, pending_apps, 50)

        return all_successful_apps, unsuccessful_apps, pending_apps


@console_permission_required('user.change_credentialapplication')
def credentialed_user_info(request, username):
    try:
        c_user = User.objects.get(username__iexact=username)
        application = CredentialApplication.objects.get(
            user=c_user, status=CredentialApplication.Status.ACCEPTED)
    except (User.DoesNotExist, CredentialApplication.DoesNotExist):
        raise Http404()
    return render(request, 'console/credentialed_user_info.html', {'c_user': c_user, 'application': application,
                                                                   'CredentialApplication': CredentialApplication})


@console_permission_required('user.can_review_training')
def training_list(request, status):
    """
    List all training applications.
    """
    trainings = Training.objects.select_related(
        'user__profile', 'training_type').order_by('-user__is_credentialed', 'application_datetime')

    training_types = TrainingType.objects.values_list("name", flat=True)

    # Allow filtering by event.
    if 'event' in request.GET:
        slug = request.GET['event']
        event = Event.objects.get(slug=slug)
        users = User.objects.filter(eventparticipant__event=event)
        trainings = trainings.filter(user__in=users)

    review_training = trainings.get_review()
    valid_training = trainings.get_valid()
    expired_training = trainings.get_expired()
    rejected_training = trainings.get_rejected()

    training_by_status = {
        'review': review_training,
        'valid': valid_training.order_by('-process_datetime'),
        'expired': expired_training,
        'rejected': rejected_training.order_by('-process_datetime'),
    }

    display_training = training_by_status[status]

    if request.method == 'POST':
        if "search" in request.POST:
            display_training = search_training_applications(request, display_training)
            template_by_status = {
                'review': 'console/review_training_table.html',
                'valid': 'console/valid_training_table.html',
                'expired': 'console/expired_training_table.html',
                'rejected': 'console/rejected_training_table.html', }
            return render(request, template_by_status[status], {'trainings': display_training, 'status': status})

    return render(
        request,
        'console/training_list.html',
        {
            'trainings': paginate(request, display_training, 50),
            'training_types': training_types,
            'status': status,
            'review_count': review_training.count(),
            'valid_count': valid_training.count(),
            'expired_count': expired_training.count(),
            'rejected_count': rejected_training.count(),
        },
    )


def search_training_applications(request, display_training):
    """
    Search training applications.

    Args:
        request (obj): Django WSGIRequest object.
        display_training (obj): Training queryset.
    """
    search_field = request.POST['search']
    if search_field:
        display_training = display_training.filter(Q(user__username__icontains=search_field)
                                                   | Q(user__profile__first_names__icontains=search_field)
                                                   | Q(user__profile__last_name__icontains=search_field)
                                                   | Q(user__email__icontains=search_field)
                                                   | Q(training_type__name__iexact=search_field))

    # prevent formatting issue if search field is empty
    if len(search_field) == 0:
        display_training = paginate(request, display_training, 50)

    return display_training


@console_permission_required('user.can_review_training')
def training_process(request, pk):
    training = get_object_or_404(Training.objects.select_related('training_type', 'user__profile').get_review(), pk=pk)

    TrainingQuestionFormSet = modelformset_factory(
        model=TrainingQuestion, form=forms.TrainingQuestionForm, formset=forms.TrainingQuestionFormSet, extra=0
    )

    if request.method == 'POST':
        if 'accept' in request.POST:
            questions_formset = TrainingQuestionFormSet(data=request.POST, queryset=training.training_questions.all())

            if questions_formset.is_valid():
                questions_formset.save()

                training.accept(reviewer=request.user)

                messages.success(request, 'The training was approved.')
                notification.process_training_complete(request, training)
                return redirect('training_list', status='review')

            training_review_form = forms.TrainingReviewForm()

        elif 'accept_all' in request.POST:

            # populate all answer fields with True
            data_copy = request.POST.copy()
            answer_fields = [key for key, val in data_copy.items() if "answer" in key]

            for field in answer_fields:
                data_copy[field] = 'True'

            questions_formset = TrainingQuestionFormSet(data=data_copy, queryset=training.training_questions.all())

            if questions_formset.is_valid():
                questions_formset.save()

                training.accept(reviewer=request.user)

                messages.success(request, 'The training was approved.')
                notification.process_training_complete(request, training)
                return redirect('training_list', status='review')

            training_review_form = forms.TrainingReviewForm()

        elif 'reject' in request.POST:
            training_review_form = forms.TrainingReviewForm(data=request.POST)

            if training_review_form.is_valid():
                training.reject(
                    reviewer=request.user, reviewer_comments=training_review_form.cleaned_data['reviewer_comments']
                )

                messages.success(request, 'The training was not approved.')
                notification.process_training_complete(request, training)
                return redirect('training_list', status='review')

            questions_formset = TrainingQuestionFormSet(queryset=training.training_questions.all())
    else:
        questions_formset = TrainingQuestionFormSet(queryset=training.training_questions.all())
        training_review_form = forms.TrainingReviewForm()

    training_info_from_pdf = services.get_info_from_certificate_pdf(training)

    return render(
        request,
        'console/training_process.html',
        {
            'training': training,
            'questions_formset': questions_formset,
            'training_review_form': training_review_form,
            'parsed_training_pdf': training_info_from_pdf,
        },
    )


@console_permission_required('user.can_review_training')
def training_detail(request, pk):
    training = get_object_or_404(Training.objects.prefetch_related('training_type'), pk=pk)

    return render(request, 'console/training_detail.html', {'training': training})


@console_permission_required('notification.change_news')
def news_console(request):
    """
    List of news items
    """
    news_items = News.objects.all().order_by('-publish_datetime')
    news_items = paginate(request, news_items, 50)
    return render(request, 'console/news_console.html',
                  {'news_items': news_items})


@console_permission_required('notification.change_news')
def news_add(request):
    if request.method == 'POST':
        form = forms.NewsForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'The news item has been added')
            return set_saved_fields_cookie(form, request.path,
                                           redirect('news_console'))
    else:
        form = forms.NewsForm()

    return render(request, 'console/news_add.html', {'form': form})


@console_permission_required('notification.change_news')
def news_search(request):
    """
    Filtered list of news items
    """

    if request.method == 'POST':
        search = request.POST['search']
        news_items = News.objects.filter(title__icontains=search).order_by('-publish_datetime')

        return render(request, 'console/news_list.html', {'news_items': news_items})

    raise Http404()


@console_permission_required('notification.change_news')
def news_edit(request, news_slug):
    try:
        news = News.objects.get(slug=news_slug)
    except News.DoesNotExist:
        raise Http404()
    saved = False
    if request.method == 'POST':
        if 'update' in request.POST:
            form = forms.NewsForm(data=request.POST, instance=news)
            if form.is_valid():
                saved = True
                form.save()
                messages.success(request, 'The news item has been updated')
        elif 'delete' in request.POST:
            news.delete()
            messages.success(request, 'The news item has been deleted')
            return redirect('news_console')
    else:
        form = forms.NewsForm(instance=news)

    response = render(request, 'console/news_edit.html', {'news': news,
                                                          'form': form})
    if saved:
        set_saved_fields_cookie(form, request.path, response)
    return response


@console_permission_required('project.can_edit_featured_content')
def featured_content(request):
    """
    List of news items
    """

    if 'add' in request.POST:
        featured = PublishedProject.objects.filter(featured__isnull=False)
        mx = max(featured.values_list('featured', flat=True), default=1)
        project = PublishedProject.objects.filter(id=request.POST['id']).update(featured=mx + 1)
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
        PublishedProject.objects.filter(featured=idx - 1).update(featured=idx)
        move.featured = idx - 1
        move.save()
    elif 'down' in request.POST:
        # Get project to be moved
        idx = int(request.POST['down'])
        move = PublishedProject.objects.get(featured=idx)

        # Sets featured to 0 (avoid constraint violation)
        move.featured = 0
        move.save()

        # Swap positions
        PublishedProject.objects.filter(featured=idx + 1).update(featured=idx)
        move.featured = idx + 1
        move.save()

    featured_content = PublishedProject.objects.select_related('resource_type').filter(
        featured__isnull=False
    ).order_by('featured')

    return render(request, 'console/featured_content.html',
                  {'featured_content': featured_content})


@console_permission_required('project.can_edit_featured_content')
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
            title__iregex=r'{0}{1}{0}'.format(wb, title),
            featured__isnull=True
        )
    else:
        form = forms.FeaturedForm()

    return render(request, 'console/add_featured.html', {'title': title,
                                                         'projects': projects,
                                                         'form': form,
                                                         'valid_search': valid_search})


@console_permission_required('project.can_view_project_guidelines')
def guidelines_review(request):
    """
    Guidelines for reviewers.
    """
    return render(request, 'console/guidelines_review.html')


@console_permission_required('project.can_view_stats')
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
    sub_ed = projects.annotate(tm=Cast(F('editor_assignment_datetime') - F('submission_datetime'),
                               DurationField())).values_list('tm', flat=True)

    for y in stats:
        y_durations = sub_ed.filter(publish_datetime__year=y)
        days = [d.days for d in y_durations if d.days >= 0]
        try:
            stats[y].append(median(days))
        except StatisticsError:
            stats[y].append(None)

    # Submission to publication
    sub_pub = projects.annotate(tm=Cast(F('publish_datetime') - F('submission_datetime'),
                                DurationField())).values_list('tm', flat=True)

    for y in stats:
        y_durations = sub_pub.filter(publish_datetime__year=y)
        days = [d.days for d in y_durations if d.days >= 0]
        try:
            stats[y].append(median(days))
        except StatisticsError:
            stats[y].append(None)

    return render(request, 'console/editorial_stats.html', {
                  'submenu': 'editorial', 'stats': stats})


@console_permission_required('project.can_view_stats')
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
        a = acc_and_rej.filter(status=CredentialApplication.Status.ACCEPTED).count()
        r = acc_and_rej.filter(status=CredentialApplication.Status.REJECTED).count()
        stats[y]['processed'] = a + r
        try:
            stats[y]['approved'] = round((100 * a) / (a + r))
        except ZeroDivisionError:
            stats[y]['approved'] = None

    # Time taken to contact the reference
    time_to_ref = apps.annotate(tm=Cast(F('reference_contact_datetime')
                                - F('application_datetime'),
                                DurationField())).values_list('tm', flat=True)
    for y in stats:
        durations = time_to_ref.filter(application_datetime__year=y)
        try:
            days = [d.days for d in durations if d and d.days >= 0]
            stats[y]['time_to_ref'] = median(days)
        except (AttributeError, StatisticsError):
            stats[y]['time_to_ref'] = None

    # Time taken for the reference to respond
    time_to_reply = apps.annotate(tm=Cast(F('reference_response_datetime')
                                  - F('reference_contact_datetime'),
                                  DurationField())).values_list('tm', flat=True)
    for y in stats:
        durations = time_to_reply.filter(application_datetime__year=y)
        try:
            days = [d.days for d in durations if d and d.days >= 0]
            stats[y]['time_to_reply'] = median(days)
        except (AttributeError, StatisticsError):
            stats[y]['time_to_reply'] = None

    # Time taken to process the application
    time_to_decision = apps.annotate(tm=Cast(F('decision_datetime')
                                     - F('application_datetime'),
                                     DurationField())).values_list('tm', flat=True)
    for y in stats:
        durations = time_to_decision.filter(application_datetime__year=y)
        try:
            days = [d.days for d in durations if d and d.days >= 0]
            stats[y]['time_to_decision'] = median(days)
        except (AttributeError, StatisticsError):
            stats[y]['time_to_decision'] = None

    return render(request, 'console/credentialing_stats.html',
                  {'submenu': 'credential',
                   'stats': stats})


@console_permission_required('project.can_view_stats')
def submission_stats(request):
    stats = OrderedDict()
    todays_date = datetime.today()
    all_projects = [PublishedProject.objects.filter(is_legacy=False), ActiveProject.objects.all()]
    cur_year = todays_date.year
    cur_month = todays_date.month

    # Get last 18 months and initialize all counts to zero
    for i in range(0, 18):
        if cur_year not in stats:
            stats[cur_year] = OrderedDict()
        month = datetime(cur_year, cur_month, 1).strftime("%B")
        stats[cur_year][month] = [0, 0, 0, 0]
        cur_month -= 1
        if cur_month == 0:
            cur_month = 12
            cur_year -= 1

    # Get all active and published projects and store their milestone datetimes
    for project_set in all_projects:

        # Get times when projects were created
        for project in project_set:
            create_yr = project.creation_datetime.year
            create_mo = project.creation_datetime.strftime("%B")
            if create_yr in stats and create_mo in stats[create_yr]:
                stats[create_yr][create_mo][0] += 1

            # Get times when projects were submitted and count unique submissions vs. resubmissions
            edit_logs = project.edit_log_history()
            for log in edit_logs:
                sub_date_yr = log.submission_datetime.year
                sub_date_mo = log.submission_datetime.strftime("%B")
                if sub_date_yr in stats and sub_date_mo in stats[sub_date_yr]:
                    if log.is_resubmission:
                        stats[sub_date_yr][sub_date_mo][2] += 1
                    else:
                        stats[sub_date_yr][sub_date_mo][1] += 1

            # Get times when projects were published, if applicable
            try:
                pub_yr = project.publish_datetime.year
                pub_mo = project.publish_datetime.strftime("%B")
                if pub_yr in stats and pub_mo in stats[pub_yr]:
                    stats[pub_yr][pub_mo][3] += 1
            except AttributeError:
                pass

    return render(request, 'console/submission_stats.html',
                  {'submenu': 'submission', 'stats': stats})


@console_permission_required('project.can_view_access_logs')
def download_credentialed_users(request):
    """
    CSV create and download for database access.
    """
    # Create the HttpResponse object with the appropriate CSV header.
    project_access = DUASignature.objects.filter(project__access_policy=AccessPolicy.CREDENTIALED)
    added = []
    dua_info_csv = [[
        'First name',
        'Last name',
        'E-mail',
        'Institution',
        'Country',
        'MIMIC approval date',
        'eICU approval date',
        'General research area for which the data will be used'
    ]]
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


@console_permission_required('project.can_view_access_logs')
def project_access_manage(request, pid):
    projects = PublishedProject.objects.prefetch_related('duasignature_set__user__profile')
    c_project = get_object_or_404(projects, id=pid, access_policy=AccessPolicy.CREDENTIALED)

    return render(request, 'console/project_access_manage.html', {
        'c_project': c_project, 'project_members': c_project.duasignature_set.all(),
    })


@console_permission_required('project.can_view_access_logs')
def project_access_requests_list(request):
    projects = PublishedProject.objects.filter(access_policy=AccessPolicy.CONTRIBUTOR_REVIEW).annotate(
        access_requests_count=Count('data_access_requests')
    ).order_by('-title')

    q = request.GET.get('q')
    if q:
        projects = projects.filter(title__icontains=q)

    projects = paginate(request, projects, 50)

    return render(request, 'console/project_access_requests_list.html', {
        'projects': projects
    })


@console_permission_required('project.can_view_access_logs')
def project_access_requests_detail(request, pk):
    project = get_object_or_404(PublishedProject, access_policy=AccessPolicy.CONTRIBUTOR_REVIEW, pk=pk)
    access_requests = DataAccessRequest.objects.filter(project=project)

    q = request.GET.get('q')
    if q:
        access_requests = access_requests.filter(requester__username__icontains=q)

    access_requests = access_requests.order_by('-request_datetime')
    access_requests = paginate(request, access_requests, 50)

    return render(request, 'console/project_access_requests_detail.html', {
        'project': project, 'access_requests': access_requests
    })


@console_permission_required('project.can_view_access_logs')
def access_request(request, pk):
    access_request = get_object_or_404(DataAccessRequest, pk=pk)

    return render(request, 'console/access_request.html', {'access_request': access_request})


@console_permission_required('project.can_view_access_logs')
def project_access_logs(request):
    c_projects = PublishedProject.objects.annotate(
        log_count=Count('logs', filter=Q(logs__category=LogCategory.ACCESS)))

    access_policy = request.GET.get('accessPolicy')
    if access_policy:
        c_projects = c_projects.filter(access_policy=access_policy)

    q = request.GET.get('q')
    if q is not None:
        c_projects = c_projects.filter(title__icontains=q)

    c_projects = paginate(request, c_projects, 50)

    return render(request, 'console/project_access_logs.html', {
        'c_projects': c_projects,
    })


@console_permission_required('project.can_view_access_logs')
def project_access_logs_detail(request, pid):
    c_project = get_object_or_404(PublishedProject, id=pid)
    logs = (
        c_project.logs.filter(category=LogCategory.ACCESS)
        .order_by("-creation_datetime")
        .select_related("user__profile")
        .annotate(duration=F("last_access_datetime") - F("creation_datetime"))
    )

    user = request.GET.get('user')
    if user:
        logs = logs.filter(user=user)

    start_date = request.GET.get('startDate')
    end_date = request.GET.get('endDate')
    if start_date and end_date:
        logs = logs.filter(creation_datetime__gte=start_date, creation_datetime__lte=end_date)

    logs = paginate(request, logs, 50)

    user_filter_form = UserFilterForm()

    return render(request, 'console/project_access_logs_detail.html', {
        'c_project': c_project, 'logs': logs,
        'user_filter_form': user_filter_form
    })


@console_permission_required('project.can_view_access_logs')
def download_project_accesses(request, pk):
    headers = ['User', 'Email address', 'First access', 'Last access', 'Duration', 'Count']

    data = (
        AccessLog.objects.filter(
            content_type=ContentType.objects.get_for_model(PublishedProject), object_id=pk
        )
        .select_related("user__profile")
        .annotate(duration=F("last_access_datetime") - F("creation_datetime"))
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="project_{pk}_accesses.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)

    for row in data:
        writer.writerow([
            row.user.get_full_name(),
            row.user.email,
            row.creation_datetime.strftime('%m/%d/%Y, %I:%M:%S %p'),
            row.last_access_datetime.strftime('%m/%d/%Y, %I:%M:%S %p'),
            str(row.duration).split('.')[0],
            row.count
        ])

    return response


@console_permission_required('project.can_view_access_logs')
def user_access_logs(request):
    users = (
        User.objects.filter(is_active=True)
        .select_related("profile")
        .annotate(logs_count=Count("logs", filter=Q(logs__category=LogCategory.ACCESS)))
    )

    q = request.GET.get('q')
    if q:
        for query in q.split('+'):
            users = users.filter(
                Q(username__icontains=query)
                | Q(profile__first_names__icontains=query)
                | Q(profile__last_name__icontains=query)
            )

    users = paginate(request, users, 50)

    return render(request, 'console/user_access_logs.html', {
        'users': users,
    })


@console_permission_required('project.can_view_access_logs')
def user_access_logs_detail(request, pid):
    user = get_object_or_404(User, id=pid, is_active=True)
    logs = (
        user.logs.filter(category=LogCategory.ACCESS)
        .order_by("-creation_datetime")
        .prefetch_related("project")
        .annotate(duration=F("last_access_datetime") - F("creation_datetime"))
    )

    project = request.GET.get('project')
    if project:
        logs = logs.filter(object_id=project, content_type=ContentType.objects.get_for_model(PublishedProject))

    start_date = request.GET.get('startDate')
    end_date = request.GET.get('endDate')
    if start_date and end_date:
        logs = logs.filter(creation_datetime__gte=start_date, creation_datetime__lte=end_date)

    logs = paginate(request, logs, 50)

    project_filter_form = ProjectFilterForm()

    return render(request, 'console/user_access_logs_detail.html', {
        'user': user, 'logs': logs,
        'project_filter_form': project_filter_form
    })


@console_permission_required('project.can_view_access_logs')
def download_user_accesses(request, pk):
    headers = ['Project name', 'First access', 'Last access', 'Duration', 'Count']

    data = (
        AccessLog.objects.filter(user=pk).select_related('user__profile')
        .annotate(duration=F('last_access_datetime') - F('creation_datetime'))
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="user_{pk}_logs.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)

    for row in data:
        writer.writerow([
            row.project,
            row.creation_datetime.strftime('%m/%d/%Y, %I:%M:%S %p'),
            row.last_access_datetime.strftime('%m/%d/%Y, %I:%M:%S %p'),
            str(row.duration).split('.')[0],
            row.count
        ])

    return response


@console_permission_required('project.can_view_access_logs')
def gcp_signed_urls_logs(request):
    projects = ActiveProject.objects.annotate(
        log_count=Count('logs', filter=Q(logs__category=LogCategory.GCP)))

    q = request.GET.get('q')
    if q:
        projects = projects.filter(title__icontains=q)

    projects = paginate(request, projects, 50)

    return render(request, 'console/gcp_logs.html', {
        'projects': projects,
    })


@console_permission_required('project.can_view_access_logs')
def gcp_signed_urls_logs_detail(request, pk):
    project = get_object_or_404(ActiveProject, pk=pk)
    logs = project.logs.order_by('-creation_datetime').prefetch_related('project').annotate(
        duration=F('last_access_datetime') - F('creation_datetime'))

    logs = paginate(request, logs, 50)

    return render(request, 'console/gcp_logs_detail.html', {
        'project': project, 'logs': logs,
    })


@console_permission_required('project.can_view_access_logs')
def download_signed_urls_logs(request, pk):
    headers = ['User', 'Email address', 'First access', 'Last access', 'Duration', 'Data', 'Count']

    data = GCPLog.objects.filter(
        content_type=ContentType.objects.get_for_model(ActiveProject),
        object_id=pk
    ).select_related('user__profile').annotate(
        duration=F('last_access_datetime') - F('creation_datetime')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="project_{pk}_signed_urls.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)

    for row in data:
        writer.writerow([
            row.user.get_full_name(),
            row.user.email,
            row.creation_datetime.strftime('%m/%d/%Y, %I:%M:%S %p'),
            row.last_access_datetime.strftime('%m/%d/%Y, %I:%M:%S %p'),
            str(row.duration).split('.')[0],
            row.data,
            row.count
        ])

    return response


class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        """
        Get all active users with usernames that match the request string,
        excluding the user who is doing the search.
        """
        qs = User.objects.filter(is_active=True)

        if self.q:
            for query in self.q.split('+'):
                qs = qs.filter(
                    Q(username__icontains=query)
                    | Q(profile__first_names__icontains=query)
                    | Q(profile__last_name__icontains=query)
                )

        return qs


class ProjectAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        """
        Get all active users with usernames that match the request string,
        excluding the user who is doing the search.
        """
        qs = PublishedProject.objects.all()

        if self.q:
            qs = qs.filter(title__icontains=self.q)

        return qs


@console_permission_required('user.change_credentialapplication')
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

    all_known_ref = CredentialApplication.objects.select_related('user__profile').filter(
        reference_contact_datetime__isnull=False).order_by(
        '-reference_contact_datetime')

    all_known_ref = paginate(request, all_known_ref, 50)

    return render(request, 'console/known_references.html', {
        'all_known_ref': all_known_ref,
    })


@console_permission_required('redirects.view_redirect')
def view_redirects(request):
    """
    Display a list of redirected URLs.
    """
    redirects = Redirect.objects.all().order_by("old_path")
    return render(
        request,
        'console/redirects.html',
        {'redirects': redirects})


@console_permission_required('physionet.change_frontpagebutton')
def frontpage_buttons(request):

    if request.method == 'POST':
        up = request.POST.get('up')
        if up:
            front_page_button = get_object_or_404(FrontPageButton, pk=up)
            front_page_button.move_up()

        down = request.POST.get('down')
        if down:
            front_page_button = get_object_or_404(FrontPageButton, pk=down)
            front_page_button.move_down()
        return HttpResponseRedirect(reverse('frontpage_buttons'))

    frontpage_buttons = FrontPageButton.objects.all()
    return render(
        request,
        'console/frontpage_button/index.html',
        {'frontpage_buttons': frontpage_buttons})


@console_permission_required('physionet.change_frontpagebutton')
def frontpage_button_add(request):
    if request.method == 'POST':
        frontpage_button_form = forms.FrontPageButtonForm(data=request.POST)
        if frontpage_button_form.is_valid():
            frontpage_button_form.save()
            messages.success(request, "The frontpage button was successfully created.")
            return HttpResponseRedirect(reverse('frontpage_buttons'))
    else:
        frontpage_button_form = forms.FrontPageButtonForm()

    return render(
        request,
        'console/frontpage_button/add.html',
        {'frontpage_button_form': frontpage_button_form},
    )


@console_permission_required('physionet.change_frontpagebutton')
def frontpage_button_edit(request, button_pk):

    frontpage_button = get_object_or_404(FrontPageButton, pk=button_pk)
    if request.method == 'POST':
        frontpage_button_form = forms.FrontPageButtonForm(instance=frontpage_button, data=request.POST)
        if frontpage_button_form.is_valid():
            frontpage_button_form.save()
            messages.success(request, "The front page was successfully edited.")
            return HttpResponseRedirect(reverse('frontpage_buttons'))
    else:
        frontpage_button_form = forms.FrontPageButtonForm(instance=frontpage_button)

    return render(
        request,
        'console/frontpage_button/edit.html',
        {
            'frontpage_button_form': frontpage_button_form,
            'button': frontpage_button
        }
    )


@console_permission_required('physionet.change_frontpagebutton')
def frontpage_button_delete(request, button_pk):
    frontpage_button = get_object_or_404(FrontPageButton, pk=button_pk)
    if request.method == 'POST':
        frontpage_button.delete()
        messages.success(request, "The front page button was successfully deleted.")

    return HttpResponseRedirect(reverse('frontpage_buttons'))


@console_permission_required('physionet.change_staticpage')
def static_pages(request):
    if request.method == 'POST':
        up = request.POST.get('up')
        if up:
            page = get_object_or_404(StaticPage, pk=up)
            page.move_up()

        down = request.POST.get('down')
        if down:
            page = get_object_or_404(StaticPage, pk=down)
            page.move_down()
        return HttpResponseRedirect(reverse('static_pages'))

    pages = StaticPage.objects.all().order_by("nav_order")
    return render(
        request,
        'console/static_page/index.html',
        {'pages': pages})


@console_permission_required('physionet.change_staticpage')
def static_page_add(request):
    if request.method == 'POST':
        static_page_form = forms.StaticPageForm(data=request.POST)
        if static_page_form.is_valid():
            static_page_form.save()
            messages.success(request, "The static page was successfully created.")
            return HttpResponseRedirect(reverse('static_pages'))
    else:
        static_page_form = forms.StaticPageForm()

    return render(
        request,
        'console/static_page/add.html',
        {'static_page_form': static_page_form},
    )


@console_permission_required('physionet.change_staticpage')
def static_page_edit(request, page_pk):

    static_page = get_object_or_404(StaticPage, pk=page_pk)
    if request.method == 'POST':
        static_page_form = forms.StaticPageForm(instance=static_page, data=request.POST)
        if static_page_form.is_valid():
            static_page_form.save()
            messages.success(request, "The static page was successfully edited.")
            return HttpResponseRedirect(reverse('static_pages'))
    else:
        static_page_form = forms.StaticPageForm(instance=static_page)

    return render(
        request,
        'console/static_page/edit.html',
        {'static_page_form': static_page_form, 'page': static_page},
    )


@console_permission_required('physionet.change_staticpage')
def static_page_delete(request, page_pk):
    static_page = get_object_or_404(StaticPage, pk=page_pk)
    if request.method == 'POST':
        static_page.delete()
        messages.success(request, "The static page was successfully deleted.")

    return HttpResponseRedirect(reverse('static_pages'))


@console_permission_required('physionet.change_staticpage')
def static_page_sections(request, page_pk):
    static_page = get_object_or_404(StaticPage, pk=page_pk)
    if request.method == 'POST':
        section_form = forms.SectionForm(data=request.POST, static_page=static_page)
        if section_form.is_valid():
            section_form.save()

        up = request.POST.get('up')
        if up is not None:
            section = get_object_or_404(Section, pk=up)
            section.move_up()

        down = request.POST.get('down')
        if down is not None:
            section = get_object_or_404(Section, pk=down)
            section.move_down()

    section_form = forms.SectionForm(static_page=static_page)

    sections = Section.objects.filter(static_page=static_page)

    return render(
        request,
        'console/static_page_sections.html',
        {'sections': sections, 'page': static_page, 'section_form': section_form},
    )


@console_permission_required('physionet.change_staticpage')
def static_page_sections_delete(request, page_pk, section_pk):
    static_page = get_object_or_404(StaticPage, pk=page_pk)
    if request.method == 'POST':
        section = get_object_or_404(Section, static_page=static_page, pk=section_pk)
        section.delete()
        Section.objects.filter(static_page=static_page, order__gt=section.order).update(order=F('order') - 1)

    return redirect('static_page_sections', page_pk=static_page.pk)


@console_permission_required('physionet.change_staticpage')
def static_page_sections_edit(request, page_pk, section_pk):
    static_page = get_object_or_404(StaticPage, pk=page_pk)
    section = get_object_or_404(Section, static_page=static_page, pk=section_pk)
    if request.method == 'POST':
        section_form = forms.SectionForm(instance=section, data=request.POST, static_page=static_page)
        if section_form.is_valid():
            section_form.save()
            return redirect('static_page_sections', page_pk=static_page.pk)
    else:
        section_form = forms.SectionForm(instance=section, static_page=static_page)

    return render(
        request,
        'console/static_page_sections_edit.html',
        {'section_form': section_form, 'page': static_page, 'section': section},
    )


@console_permission_required('project.add_license')
def license_list(request):
    if request.method == 'POST':
        license_form = forms.LicenseForm(data=request.POST)
        if license_form.is_valid():
            license_form.save()
            license_form = forms.LicenseForm()
            messages.success(request, "The license has been created.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        license_form = forms.LicenseForm()

    licenses = License.objects.prefetch_related('project_types').order_by('access_policy', 'name', '-version')
    licenses = paginate(request, licenses, 20)

    return render(
        request,
        'console/license_list.html',
        {'licenses': licenses, 'license_form': license_form}
    )


@console_permission_required('project.add_license')
def license_detail(request, pk):
    license = get_object_or_404(License, pk=pk)

    if request.method == 'POST':
        license_form = forms.LicenseForm(data=request.POST, instance=license)
        if license_form.is_valid():
            license_form.save()
            messages.success(request, "The license has been updated.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")

    else:
        license_form = forms.LicenseForm(instance=license)

    return render(
        request,
        'console/license_detail.html',
        {'license': license, 'license_form': license_form}
    )


@console_permission_required('project.add_license')
def license_delete(request, pk):
    if request.method == 'POST':
        license = get_object_or_404(License, pk=pk)
        license.delete()

    return redirect('license_list')


@console_permission_required('project.add_license')
def license_new_version(request, pk):
    license = get_object_or_404(License, pk=pk)

    if request.method == 'POST':
        license_form = forms.LicenseForm(data=request.POST)
        if license_form.is_valid():
            license_form.save()
            messages.success(request, "The license has been created.")
            return redirect("license_list")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        license_data = model_to_dict(license)
        license_data['id'] = None
        license_data['version'] = None
        license_form = forms.LicenseForm(initial=license_data)

    return render(
        request,
        'console/license_new_version.html',
        {'license': license, 'license_form': license_form}
    )


@console_permission_required('project.add_dua')
def dua_list(request):
    if request.method == 'POST':
        dua_form = forms.DUAForm(data=request.POST)
        if dua_form.is_valid():
            dua_form.save()
            dua_form = forms.DUAForm()
            messages.success(request, "The DUA has been created.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        dua_form = forms.DUAForm()

    duas = DUA.objects.order_by('access_policy', 'name')
    duas = paginate(request, duas, 20)

    return render(request, 'console/dua_list.html', {'duas': duas, 'dua_form': dua_form})


@console_permission_required('project.add_dua')
def dua_detail(request, pk):
    dua = get_object_or_404(DUA, pk=pk)

    if request.method == 'POST':
        dua_form = forms.DUAForm(data=request.POST, instance=dua)
        if dua_form.is_valid():
            dua_form.save()
            messages.success(request, "The dua has been created.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")

    else:
        dua_form = forms.DUAForm(instance=dua)

    return render(request, 'console/dua_detail.html', {'dua': dua, 'dua_form': dua_form})


@console_permission_required('project.add_dua')
def dua_delete(request, pk):
    if request.method == 'POST':
        dua = get_object_or_404(DUA, pk=pk)
        dua.delete()

    return redirect("dua_list")


@console_permission_required('project.add_dua')
def dua_new_version(request, pk):
    dua = get_object_or_404(DUA, pk=pk)

    if request.method == 'POST':
        dua_form = forms.DUAForm(data=request.POST)
        if dua_form.is_valid():
            dua_form.save()
            messages.success(request, "The DUA has been created.")
            return redirect("dua_list")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        dua_data = model_to_dict(dua)
        dua_data['id'] = None
        dua_data['version'] = None
        dua_form = forms.DUAForm(initial=dua_data)

    return render(request, 'console/dua_new_version.html', {'dua': dua, 'dua_form': dua_form})


@console_permission_required('project.add_codeofconduct')
def code_of_conduct_list(request):
    if request.method == 'POST':
        code_of_conduct_form = forms.CodeOfConductForm(data=request.POST)
        if code_of_conduct_form.is_valid():
            code_of_conduct_form.save()
            code_of_conduct_form = forms.CodeOfConductForm()
            messages.success(request, "The Code of Conduct has been created.")
            return redirect("code_of_conduct_list")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        code_of_conduct_form = forms.CodeOfConductForm()
    code_of_conducts = CodeOfConduct.objects.order_by('name', 'version')
    code_of_conducts = paginate(request, code_of_conducts, 20)

    return render(
        request,
        'console/code_of_conduct_list.html',
        {
            'code_of_conducts': code_of_conducts,
            'code_of_conduct_form': code_of_conduct_form,
        },
    )


@console_permission_required('project.add_codeofconduct')
def code_of_conduct_detail(request, pk):
    code_of_conduct = get_object_or_404(CodeOfConduct, pk=pk)
    if request.method == 'POST':
        code_of_conduct_form = forms.CodeOfConductForm(data=request.POST, instance=code_of_conduct)
        if code_of_conduct_form.is_valid():
            code_of_conduct_form.save()
            messages.success(request, "The Code of Conduct has been updated.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")

    else:
        code_of_conduct_form = forms.CodeOfConductForm(instance=code_of_conduct)

    return render(
        request,
        'console/code_of_conduct_detail.html',
        {
            'code_of_conduct': code_of_conduct,
            'code_of_conduct_form': code_of_conduct_form,
        },
    )


@console_permission_required('project.add_codeofconduct')
def code_of_conduct_delete(request, pk):
    if request.method == 'POST':
        code_of_conduct = get_object_or_404(CodeOfConduct, pk=pk)
        code_of_conduct.delete()

    return redirect("code_of_conduct_list")


@console_permission_required('project.add_codeofconduct')
def code_of_conduct_new_version(request, pk):
    code_of_conduct = get_object_or_404(CodeOfConduct, pk=pk)
    if request.method == 'POST':
        code_of_conduct_form = forms.CodeOfConductForm(data=request.POST)
        if code_of_conduct_form.is_valid():
            code_of_conduct_form.save()
            messages.success(request, "The Code of Conduct has been created.")
            return redirect("code_of_conduct_list")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        code_of_conduct_data = model_to_dict(code_of_conduct)
        code_of_conduct_data['id'] = None
        code_of_conduct_data['version'] = None
        code_of_conduct_form = forms.CodeOfConductForm(initial=code_of_conduct_data)

    return render(
        request,
        'console/code_of_conduct_new_version.html',
        {
            'code_of_conduct': code_of_conduct,
            'code_of_conduct_form': code_of_conduct_form,
        },
    )


@console_permission_required('project.add_codeofconduct')
def code_of_conduct_activate(request, pk):
    CodeOfConduct.objects.filter(is_active=True).update(is_active=False)

    code_of_conduct = get_object_or_404(CodeOfConduct, pk=pk)
    code_of_conduct.is_active = True
    code_of_conduct.save()

    messages.success(request, f"The {code_of_conduct.name} has been activated.")

    return redirect("code_of_conduct_list")


@console_permission_required('user.view_all_events')
def event_active(request):
    """
    List of events
    """
    event_active = Event.objects.filter(end_date__gte=timezone.now())
    event_active = paginate(request, event_active, 50)

    return render(request, 'console/event_active.html',
                  {'event_active': event_active,
                   'nav_event_active': True
                   })


@console_permission_required('user.view_all_events')
def event_archive(request):
    """
    List of archived events
    """
    event_archive = Event.objects.filter(end_date__lte=timezone.now())
    event_archive = paginate(request, event_archive, 50)

    return render(request, 'console/event_archive.html',
                  {'event_archive': event_archive,
                   'nav_event_archive': True
                   })


@console_permission_required('user.view_all_events')
def event_management(request, event_slug):
    """
    Admin page for managing an individual Event.
    """
    selected_event = get_object_or_404(Event, slug=event_slug)

    # handle the add dataset form(s)
    if request.method == "POST":
        if "add-event-dataset" in request.POST.keys():
            event_dataset_form = EventDatasetForm(request.POST)
            if event_dataset_form.is_valid():
                active_datasets = selected_event.datasets.filter(
                    dataset=event_dataset_form.cleaned_data["dataset"],
                    access_type=event_dataset_form.cleaned_data["access_type"],
                    is_active=True)
                if active_datasets.count() == 0:
                    event_dataset_form.instance.event = selected_event
                    event_dataset_form.save()
                    messages.success(
                        request, "The dataset has been added to the event."
                    )
                else:
                    messages.error(
                        request, "The dataset has already been added to the event."
                    )
            else:
                messages.error(request, event_dataset_form.errors)

            return redirect("event_management", event_slug=event_slug)
        elif "remove-event-dataset" in request.POST.keys():
            event_dataset_id = request.POST["remove-event-dataset"]
            event_dataset = get_object_or_404(EventDataset, pk=event_dataset_id)
            event_dataset.revoke_dataset_access()
            messages.success(request, "The dataset has been removed from the event.")

            return redirect("event_management", event_slug=event_slug)
    else:
        event_dataset_form = EventDatasetForm()

    participants = selected_event.participants.all()
    pending_applications = selected_event.applications.filter(
        status=EventApplication.EventApplicationStatus.WAITLISTED
    )
    rejected_applications = selected_event.applications.filter(
        status=EventApplication.EventApplicationStatus.NOT_APPROVED
    )
    withdrawn_applications = selected_event.applications.filter(
        status=EventApplication.EventApplicationStatus.WITHDRAWN
    )

    event_datasets = selected_event.datasets.filter(is_active=True)
    applicant_info = [
        {
            "id": "participants",
            "title": "Total participants:",
            "count": len(participants),
            "objects": participants,
        },
        {
            "id": "pending_applications",
            "title": "Pending applications:",
            "count": len(pending_applications),
            "objects": pending_applications,
        },
        {
            "id": "rejected_applications",
            "title": "Rejected applications:",
            "count": len(rejected_applications),
            "objects": rejected_applications,
        },
        {
            "id": "withdrawn_applications",
            "title": "Withdrawn applications:",
            "count": len(withdrawn_applications),
            "objects": withdrawn_applications,
        },
    ]

    return render(
        request,
        "console/event_management.html",
        {
            "event": selected_event,
            "event_dataset_form": event_dataset_form,
            "event_datasets": event_datasets,
            "applicant_info": applicant_info,
            "participants": participants,
        },
    )


@console_permission_required('events.add_eventagreement')
def event_agreement_list(request):
    if request.method == 'POST':
        event_agreement_form = EventAgreementForm(data=request.POST)
        if event_agreement_form.is_valid():
            event_agreement_form.instance.creator = request.user
            event_agreement_form.save()
            event_agreement_form = EventAgreementForm()
            messages.success(request, "The Event Agreement has been created.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        event_agreement_form = EventAgreementForm()

    event_agreements = EventAgreement.objects.filter(creator=request.user).order_by('name')
    event_agreements = paginate(request, event_agreements, 20)

    return render(
        request,
        'console/event_agreement_list.html',
        {
            'event_agreements': event_agreements,
            'event_agreement_form': event_agreement_form
        }
    )


@console_permission_required('events.add_eventagreement')
def event_agreement_new_version(request, pk):
    event_agreement = get_object_or_404(EventAgreement, pk=pk)

    if request.method == 'POST':
        event_agreement_form = EventAgreementForm(data=request.POST)
        if event_agreement_form.is_valid():
            event_agreement_form.instance.creator = request.user
            event_agreement_form.save()
            messages.success(request, "The Event Agreement has been created.")
            return redirect("event_agreement_list")
        else:
            messages.error(request, "Invalid submission. Check errors below.")
    else:
        event_agreement_data = model_to_dict(event_agreement)
        event_agreement_data['id'] = None
        event_agreement_data['version'] = None
        event_agreement_form = EventAgreementForm(initial=event_agreement_data)

    return render(
        request,
        'console/event_agreement_new_version.html',
        {
            'event_agreement': event_agreement,
            'event_agreement_form': event_agreement_form
        }
    )


@console_permission_required('events.add_eventagreement')
def event_agreement_detail(request, pk):
    event_agreement = get_object_or_404(EventAgreement, pk=pk)

    if request.method == 'POST':
        event_agreement_form = EventAgreementForm(data=request.POST, instance=event_agreement)
        if event_agreement_form.is_valid():
            event_agreement_form.save()
            messages.success(request, "The Event Agreement has been updated.")
        else:
            messages.error(request, "Invalid submission. Check errors below.")

    else:
        event_agreement_form = EventAgreementForm(instance=event_agreement)

    return render(
        request,
        'console/event_agreement_detail.html',
        {
            'event_agreement': event_agreement,
            'event_agreement_form': event_agreement_form
        }
    )


@console_permission_required('events.add_eventagreement')
def event_agreement_delete(request, pk):
    if request.method == 'POST':
        event_agreement = get_object_or_404(EventAgreement, pk=pk)
        event_agreement.delete()
        messages.success(request, "The Event Agreement has been deleted.")

    return redirect("event_agreement_list")
