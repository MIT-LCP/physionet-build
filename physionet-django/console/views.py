import pdb

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sites.shortcuts import get_current_site
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404
from django.shortcuts import redirect, render
from django.template import loader
from django.utils import timezone

from . import forms
import notification.utility as notification
from project.models import ActiveProject, ResubmissionLog, StorageRequest, SubmissionLog
from user.models import User


def is_admin(user, *args, **kwargs):
    return user.is_admin


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

    # Need to filter this by submission datetime
    projects = ActiveProject.objects.filter(submission_status__gt=0).order_by(
        'submission_datetime')

    # Separate projects by submission status
    # Awaiting editor assignment
    a_projects = projects.filter(submission_status=10)
    # Awaiting editor decision
    b_projects = projects.filter(submission_status=20)
    # Awaiting author revisions
    c_projects = projects.filter(submission_status=30)
    # Awaiting editor copyedit
    # Awaiting author approval
    # Awaiting editor publish

    assign_editor_form = forms.AssignEditorForm()

    return render(request, 'console/submitted_projects.html',
        {'projects':projects,
         'assign_editor_form':assign_editor_form,
         'a_projects':a_projects,
         'b_projects':b_projects,
         'c_projects':c_projects,
         })


@login_required
@user_passes_test(is_admin)
def editor_home(request):
    """
    List of submissions the editor is responsible for
    """
    projects = ActiveProject.objects.filter(editor=request.user).order_by(
        'submission_datetime')

    # awaiting editor decision
    a_projects = projects.filter(submission_status=20)
    # awaiting author revisions
    b_projects = projects.filter(submission_status=30)
    # awaiting editor
    c_projects = projects.filter(submission_status=40)
    return render(request, 'console/editor_home.html',
        {'a_projects':a_projects, 'b_projects':b_projects,
         'c_projects':c_projects})


@login_required
@user_passes_test(is_admin)
def edit_submission(request, project_slug):
    """
    Page to respond to a particular submission, as an editor
    """
    project = ActiveProject.objects.get(slug=project_slug)
    submission_log = project.submission_log.get()
    # The user must be the editor
    if request.user != project.editor or project.submission_status not in [20, 30]:
        return Http404()

    if request.method == 'POST':
        edit_submission_form = forms.EditSubmissionForm(
            instance=submission_log, data=request.POST)
        if edit_submission_form.is_valid():
            # This processes the resulting decision
            submission_log = edit_submission_form.save()
            # Resubmit with changes
            if submission_log.decision == 0:
                notification.edit_resubmit_notify(request, submission_log)
            # Reject
            elif submission_log.decision == 1:
                notification.edit_reject_notify(request, submission_log)
            # Accept
            else:
                notification.edit_accept_notify(request, submission_log)

            return render(request, 'console/edit_complete.html',
                {'decision':submission_log.decision,
                 'project':project, 'submission_log':submission_log})
        else:
            messages.error(request, 'Invalid response. See form below.')
    else:
        edit_submission_form = forms.EditSubmissionForm(instance=submission_log)

    return render(request, 'console/edit_submission.html',
        {'project':project, 'submission_log':submission_log,
         'edit_submission_form':edit_submission_form})


@login_required
@user_passes_test(is_admin)
def copyedit_submission(request, submission_id):
    """
    Page to copyedit the submission
    """
    submission = SubmissionLog.objects.get(id=submission_id)
    if request.user != submission.editor or submission.status != 3:
        return Http404()

    project = submission.project
    authors = project.authors.all()

    if request.method == 'POST':
        if 'complete_copyedit' in request.POST:
            submission.status = 4
            submission.copyedit_datetime = timezone.now()
            submission.save()
            notification.copyedit_complete_notify(request, submission)
            return render(request, 'console/copyedit_complete.html',
                {'submission':submission})

    author_emails = ';'.join(a.user.email for a in authors)
    authors_approved = submission.all_authors_approved()

    return render(request, 'console/copyedit_submission.html', {
        'project':project, 'submission':submission, 'authors':authors,
        'authors_approved':authors_approved, 'author_emails':author_emails})


@login_required
@user_passes_test(is_admin)
def publish_submission(request, submission_id):
    """
    Page to publish the submission
    """
    submission = SubmissionLog.objects.get(id=submission_id)
    if submission.status != 4:
        return Http404()

    project = submission.project

    if request.method == 'POST':
        if project.is_publishable():
            published_project = project.publish()
            notification.publish_notify(request, project, published_project)
            return render(request, 'console/publish_complete.html',
                {'published_project':published_project})

    publishable = project.is_publishable()
    return render(request, 'console/publish_submission.html', {
        'submission':submission, 'publishable':publishable})


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
                    core_project.storage_allowance = storage_request.request_allowance * 1024
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
    projects = ActiveProject.objects.filter(submission_status=0)
    # title, submitting author, creation date, published,
    return render(request, 'console/unsubmitted_projects.html',
        {'projects':projects})


@login_required
@user_passes_test(is_admin)
def users(request):
    """
    List of users
    """
    users = User.objects.all()
    return render(request, 'console/users.html', {'users':users})
