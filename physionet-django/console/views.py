import pdb

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.contrib.sites.shortcuts import get_current_site
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404
from django.shortcuts import redirect, render
from django.template import loader
from django.urls import reverse
from django.utils import timezone

from . import forms
import notification.utility as notification
import project.forms as project_forms
from project.models import ActiveProject, ArchivedProject, StorageRequest, EditLog, Reference, Topic, Publication, PublishedProject
from project.views import get_file_forms, get_project_file_info, process_files_post
from project.utility import get_storage_info
from user.models import User


def is_admin(user, *args, **kwargs):
    return user.is_admin

def handling_editor(base_view):
    """
    Access decorator. The user must be the editor of the project.
    """
    @login_required
    def handling_view(request, *args, **kwargs):
        user = request.user
        project = ActiveProject.objects.get(slug=kwargs['project_slug'])
        if user.is_admin and user == project.editor:
            kwargs['project'] = project
            return base_view(request, *args, **kwargs)
        raise Http404('Unable to access page')
    return handling_view

# ------------------------- Views begin ------------------------- #


@login_required
@user_passes_test(is_admin)
def console_home(request):
    return redirect('submitted_projects')


@login_required
@user_passes_test(is_admin)
def submitted_projects(request):
    """
    List of active submissions. Editors are assigned here.
    """
    if request.method == 'POST':
        assign_editor_form = forms.AssignEditorForm(request.POST)
        if assign_editor_form.is_valid():
            # Move this into project method
            project = assign_editor_form.cleaned_data['project']
            project.assign_editor(assign_editor_form.cleaned_data['editor'])
            notification.assign_editor_notify(project)
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

    return render(request, 'console/submitted_projects.html',
        {
         'assign_editor_form':assign_editor_form,
         'assignment_projects':assignment_projects,
         'decision_projects':decision_projects,
         'revision_projects':revision_projects,
         'copyedit_projects':copyedit_projects,
         'approval_projects':approval_projects,
         'publish_projects':publish_projects
         })


@login_required
@user_passes_test(is_admin)
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

    return render(request, 'console/editor_home.html',
        {'decision_projects':decision_projects,
         'revision_projects':revision_projects,
         'copyedit_projects':copyedit_projects,
         'approval_projects':approval_projects,
         'publish_projects':publish_projects})


def submission_info_redirect(request, project_slug):
    return redirect('submission_info', project_slug=project_slug)


@login_required
@user_passes_test(is_admin)
def submission_info(request, project_slug):
    """
    View information about a project under submission
    """
    project = ActiveProject.objects.get(slug=project_slug)
    authors, author_emails, storage_info, edit_logs, copyedit_logs = project.info_card()

    return render(request, 'console/submission_info.html',
        {'project':project, 'authors':authors, 'author_emails':author_emails,
         'storage_info':storage_info, 'edit_logs':edit_logs,
         'copyedit_logs':copyedit_logs})


@handling_editor
def edit_submission(request, project_slug, *args, **kwargs):
    """
    Page to respond to a particular submission, as an editor
    """
    project = kwargs['project']
    edit_log = project.edit_logs.get(decision_datetime__isnull=True)

    # The user must be the editor
    if project.submission_status not in [20, 30]:
        return Http404()

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
                {'decision':edit_log.decision,
                 'project':project, 'edit_log':edit_log})
        else:
            messages.error(request, 'Invalid response. See form below.')
    else:
        edit_submission_form = forms.EditSubmissionForm(
            resource_type=project.resource_type, instance=edit_log)

    authors, author_emails, storage_info, edit_logs, _ = project.info_card()

    return render(request, 'console/edit_submission.html',
        {'project':project,
         'edit_submission_form':edit_submission_form,
         'authors':authors,
         'author_emails':author_emails, 'storage_info':storage_info,
         'edit_logs':edit_logs})


@handling_editor
def copyedit_submission(request, project_slug, *args, **kwargs):
    """
    Page to copyedit the submission
    """
    project = kwargs['project']
    if project.submission_status != 40:
        return Http404()

    copyedit_log = project.copyedit_logs.get(complete_datetime=None)

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

    description_form = project_forms.MetadataForm(
        resource_type=project.resource_type, instance=project)
    access_form = project_forms.AccessMetadataForm(instance=project)
    reference_formset = ReferenceFormSet(instance=project)
    publication_formset = PublicationFormSet(instance=project)
    topic_formset = TopicFormSet(instance=project)

    copyedit_form = forms.CopyeditForm(instance=copyedit_log)

    if request.method == 'POST':
        if 'edit_metadata' in request.POST:
            description_form = project_forms.MetadataForm(
                resource_type=project.resource_type, data=request.POST,
                instance=project)
            access_form = project_forms.AccessMetadataForm(data=request.POST,
                instance=project)
            reference_formset = ReferenceFormSet(data=request.POST,
                instance=project)
            publication_formset = PublicationFormSet(request.POST,
                                                 instance=project)
            topic_formset = TopicFormSet(request.POST, instance=project)
            if (description_form.is_valid() and access_form.is_valid()
                                            and reference_formset.is_valid()
                                            and publication_formset.is_valid()
                                            and topic_formset.is_valid()):
                description_form.save()
                access_form.save()
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
        elif 'complete_copyedit' in request.POST:
            copyedit_form = forms.CopyeditForm(request.POST,
                instance=copyedit_log)
            if copyedit_form.is_valid():
                copyedit_log = copyedit_form.save()
                notification.copyedit_complete_notify(request, project,
                    copyedit_log)
                return render(request, 'console/copyedit_complete.html',
                    {'project':project, 'copyedit_log':copyedit_log})
            else:
                messages.error(request, 'Invalid submission. See errors below.')
        else:
            # process the file manipulation post
            subdir = process_files_post(request, project)

    if 'subdir' not in vars():
        subdir = ''

    authors, author_emails, storage_info, edit_logs, copyedit_logs = project.info_card()

    (upload_files_form, create_folder_form, rename_item_form,
        move_items_form, delete_items_form) = get_file_forms(project=project,
        subdir=subdir)

    display_files, display_dirs, dir_breadcrumbs, _ = get_project_file_info(
        project=project, subdir=subdir)

    edit_url = reverse('edit_metadata_item', args=[project.slug])

    return render(request, 'console/copyedit_submission.html', {
        'project':project, 'description_form':description_form,
        'access_form':access_form, 'reference_formset':reference_formset,
        'publication_formset':publication_formset,
        'topic_formset':topic_formset,
        'storage_info':storage_info, 'upload_files_form':upload_files_form,
        'create_folder_form':create_folder_form,
        'rename_item_form':rename_item_form,
        'move_items_form':move_items_form,
        'delete_items_form':delete_items_form,
        'subdir':subdir, 'display_files':display_files,
        'display_dirs':display_dirs, 'dir_breadcrumbs':dir_breadcrumbs,
        'is_editor':True, 'copyedit_form':copyedit_form,
        'authors':authors, 'author_emails':author_emails,
        'storage_info':storage_info, 'edit_logs':edit_logs, 'copyedit_logs':copyedit_logs,
        'add_item_url':edit_url, 'remove_item_url':edit_url})


@handling_editor
def awaiting_authors(request, project_slug, *args, **kwargs):
    """
    View the authors who have and have not approved the project for
    publication.

    Also the page to reopen the project for copyediting.
    """
    project = kwargs['project']

    authors, author_emails, storage_info, edit_logs, copyedit_logs = project.info_card()
    outstanding_emails = ';'.join([a.user.email for a in authors.filter(
        approval_datetime=None)])

    if request.method == 'POST' and 'reopen_copyedit' in request.POST:
        if project.submission_status == 50:
            project.reopen_copyedit()
            notification.reopen_copyedit_notify(request, project)
            return render(request, 'console/reopen_copyedit_complete.html',
                {'project':project})

    return render(request, 'console/awaiting_authors.html',
        {'project':project, 'authors':authors,
         'author_emails':author_emails, 'storage_info':storage_info,
         'edit_logs':edit_logs, 'copyedit_logs':copyedit_logs,
         'outstanding_emails':outstanding_emails})


@handling_editor
def publish_submission(request, project_slug, *args, **kwargs):
    """
    Page to publish the submission
    """
    project = kwargs['project']
    authors, author_emails, storage_info, edit_logs, copyedit_logs = project.info_card()
    if request.method == 'POST':
        if project.is_publishable():
            published_project = project.publish()
            notification.publish_notify(request, published_project)
            return render(request, 'console/publish_complete.html',
                {'published_project':published_project})

    publishable = project.is_publishable()
    return render(request, 'console/publish_submission.html',
        {'project':project, 'publishable':publishable, 'authors':authors,
         'author_emails':author_emails, 'storage_info':storage_info,
         'edit_logs':edit_logs, 'copyedit_logs':copyedit_logs})


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
@user_passes_test(is_admin)
def storage_requests(request):
    """
    Page for listing and responding to project storage requests
    """
    StorageResponseFormSet = modelformset_factory(StorageRequest,
        fields=('response', 'response_message'),
        widgets={'response':Select(choices=forms.RESPONSE_CHOICES),
                 'response_message':Textarea()}, extra=0)

    if request.method == 'POST':
        storage_response_formset = StorageResponseFormSet(request.POST)
        process_storage_response(request, storage_response_formset)

    storage_response_formset = StorageResponseFormSet(
        queryset=StorageRequest.objects.filter(is_active=True))

    return render(request, 'console/storage_requests.html',
        {'storage_response_formset':storage_response_formset})


@login_required
@user_passes_test(is_admin)
def unsubmitted_projects(request):
    """
    List of unsubmitted projects
    """
    projects = ActiveProject.objects.filter(submission_status=0).order_by(
        'creation_datetime')
    return render(request, 'console/unsubmitted_projects.html',
        {'projects':projects})


@login_required
@user_passes_test(is_admin)
def published_projects(request):
    """
    List of published projects
    """
    projects = PublishedProject.objects.all().order_by('publish_datetime')
    return render(request, 'console/published_projects.html',
        {'projects':projects})

@login_required
@user_passes_test(is_admin)
def rejected_submissions(request):
    """
    List of rejected submissions
    """
    projects = ArchivedProject.objects.filter(archive_reason=3).order_by('archive_datetime')
    return render(request, 'console/rejected_submissions.html',
        {'projects':projects})


@login_required
@user_passes_test(is_admin)
def users(request):
    """
    List of users
    """
    users = User.objects.all()
    return render(request, 'console/users.html', {'users':users})
