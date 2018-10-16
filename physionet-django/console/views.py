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
    return redirect('active_submissions')


@login_required
@user_passes_test(is_admin)
def active_submissions(request):
    """
    List of active submissions. Editors are assigned here.
    """
    if request.method == 'POST':
        assign_editor_form = forms.AssignEditorForm(request.POST)
        if assign_editor_form.is_valid():
            submission = assign_editor_form.cleaned_data['submission']
            submission.editor = assign_editor_form.cleaned_data['editor']
            submission.save()
            notification.assign_editor_notify(submission)
            messages.success(request, 'The editor has been assigned')

    projects = ActiveProject.objects.filter(submission_status__gt=0).order_by('submission_status')
    n_active = len(projects)
    n_awaiting_editor = submissions.filter(status=0, editor__isnull=True).count()
    n_awaiting_decision = submissions.filter(status=0, editor__isnull=False).count()
    n_awaiting_copyedit = submissions.filter(status=3).count()
    n_awaiting_publish = submissions.filter(status=5).count()

    assign_editor_form = forms.AssignEditorForm()

    return render(request, 'console/active_submissions.html',
        {'submissions':submissions, 'assign_editor_form':assign_editor_form,
         'n_active':n_active, 'n_awaiting_editor':n_awaiting_editor,
         'n_awaiting_decision':n_awaiting_decision,
         'n_awaiting_copyedit':n_awaiting_copyedit,
         'n_awaiting_publish':n_awaiting_publish})


@login_required
@user_passes_test(is_admin)
def editing_submissions(request):
    """
    List of submissions the editor is responsible for
    """
    submissions = SubmissionLog.objects.filter(is_active=True,
        editor=request.user)

    return render(request, 'console/editing_submissions.html',
        {'submissions':submissions})


@login_required
@user_passes_test(is_admin)
def edit_submission(request, submission_id):
    """
    Page to respond to a particular submission, as an editor
    """
    submission = SubmissionLog.objects.get(id=submission_id)
    project = submission.project
    # The user must be the editor
    if request.user != submission.editor or submission.status not in [0, 2]:
        return Http404()

    if request.method == 'POST':
        edit_submission_form = forms.EditSubmissionLogForm(instance=submission,
                                                        data=request.POST)
        if edit_submission_form.is_valid():
            submission = edit_submission_form.save()
            # Resubmit with changes
            if submission.decision == 1:
                notification.edit_resubmit_notify(request, submission)
            # Reject
            elif submission.decision == 2:
                notification.edit_reject_notify(request, submission)
            # Accept
            else:
                notification.edit_accept_notify(request, submission)

            return render(request, 'console/edit_complete.html',
                {'decision':submission.decision,
                 'project':project, 'submission':submission})

    edit_submission_form = forms.EditSubmissionLogForm()

    return render(request, 'console/edit_submission.html',
        {'submission':submission, 'edit_submission_form':edit_submission_form})


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
def project_list(request):
    """
    View list of projects
    """
    projects = ActiveProject.objects.all()

    # title, submitting author, creation date, published,
    return render(request, 'console/project_list.html', {'projects':projects})


@login_required
@user_passes_test(is_admin)
def user_list(request):
    """
    View list of users
    """
    users = User.objects.all()
    return render(request, 'console/user_list.html', {'users':users})
