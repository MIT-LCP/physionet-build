import pdb

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404
from django.shortcuts import redirect, render
from django.template import loader
from django.utils import timezone

from . import forms
from project.models import Project, Resubmission, StorageRequest, Submission
from user.models import User


RESPONSE_ACTIONS = {0:'rejected', 1:'accepted'}

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
            # Send the notifying emails to authors
            subject = 'Editor assigned to project {0}'.format(submission.project.title)
            for email, name in submission.project.get_author_info():
                body = loader.render_to_string(
                    'console/email/assign_editor_notify.html',
                    {'name':name, 'project':submission.project,
                     'editor':submission.editor})
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                          [email], fail_silently=False)
            messages.success(request, 'The editor has been assigned')

    submissions = Submission.objects.filter(is_active=True).order_by('status')
    assign_editor_form = forms.AssignEditorForm()
    n_awaiting_editor = submissions.filter(status=0, editor=None).count()

    return render(request, 'console/active_submissions.html',
        {'submissions':submissions, 'assign_editor_form':assign_editor_form,
         'n_awaiting_editor':n_awaiting_editor})


@login_required
@user_passes_test(is_admin)
def editing_submissions(request):
    """
    List of submissions the editor is responsible for
    """
    submissions = Submission.objects.filter(is_active=True,
        editor=request.user)

    return render(request, 'console/editing_submissions.html',
        {'submissions':submissions})


@login_required
@user_passes_test(is_admin)
def edit_submission(request, submission_id):
    """
    Page to respond to a particular submission, as an editor
    """
    submission = Submission.objects.get(id=submission_id)
    project = submission.project
    # The user must be the editor
    if request.user != submission.editor:
        return Http404()

    if request.method == 'POST':
        edit_submission_form = forms.EditSubmissionForm(instance=submission,
                                                        data=request.POST)
        if edit_submission_form.is_valid():
            submission = edit_submission_form.save()
            # Resubmit with changes
            if submission.decision == 1:
                # Notify authors of decision
                subject = 'Resubmission request for project {0}'.format(project.title)
                for email, name in submission.project.get_author_info():
                    body = loader.render_to_string(
                        'console/email/resubmit_submission_notify.html',
                        {'name':name, 'project':project,
                         'editor_comments':submission.editor_comments,
                         'domain':get_current_site(request)})
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                              [email], fail_silently=False)
            # Reject
            elif submission.decision == 2:
                # Notify authors of decision
                subject = 'Submission rejected for project {0}'.format(project.title)
                for email, name in submission.project.get_author_info():
                    body = loader.render_to_string(
                        'console/email/reject_submission_notify.html',
                        {'name':name, 'project':project,
                         'editor_comments':submission.editor_comments,
                         'domain':get_current_site(request)})
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                              [email], fail_silently=False)
            # Accept
            else:
                # Notify authors of decision
                subject = 'Submission accepted for project {0}'.format(project.title)
                for email, name in submission.project.get_author_info():
                    body = loader.render_to_string(
                        'console/email/accept_submission_notify.html',
                        {'name':name, 'project':project,
                         'editor_comments':submission.editor_comments,
                         'domain':get_current_site(request)})
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                              [email], fail_silently=False)

            return render(request, 'console/edit_complete.html',
                {'decision':submission.decision,
                 'project':project})

    edit_submission_form = forms.EditSubmissionForm()

    return render(request, 'console/edit_submission.html',
        {'submission':submission, 'edit_submission_form':edit_submission_form})


@login_required
@user_passes_test(is_admin)
def copyedit_submission(request, submission_id):
    """
    Page to copyedit the submission
    """
    submission = Submission.objects.get(id=submission_id)
    if submission.status != 3:
        return Http404()

    project = submission.project

    if request.method == 'POST':
        if 'complete_copyedit' in request.POST:
            submission.status = 4
            submission.save()
            return render(request, 'console/copyedit_complete.html')

    return render(request, 'console/copyedit_submission.html', {
        'project':project, 'submission':submission})


@login_required
@user_passes_test(is_admin)
def publish_submission(request, submission_id):
    """
    Page to publish the submission
    """
    submission = Submission.objects.get(id=submission_id)
    if submission.status != 3:
        return Http404()

    project = submission.project

    if request.method == 'POST':
        if project.is_publishable():
            submission.status = 4
            submission.save()
            return render(request, 'console/publish_complete.html')

    return render(request, 'console/publish_submission.html', {
        'project':project, 'submission':submission})


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

                project = storage_request.project

                if storage_request.response:
                    project.storage_allowance = storage_request.request_allowance
                    project.save()

                # Send the notifying email to the submitting author
                response = RESPONSE_ACTIONS[storage_request.response]
                subject = 'Storage request {0} for project {1}'.format(response,
                    project.title)
                email, name = project.get_submitting_author_info()
                body = loader.render_to_string('console/email/storage_response_notify.html',
                    {'name':name, 'project':project, 'response':response,
                     'allowance':storage_request.request_allowance})
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                          [email], fail_silently=False)
                messages.success(request, 'The storage request has been {0}.'.format(response))

@login_required
@user_passes_test(is_admin)
def storage_requests(request):
    """
    Page for listing and responding to project storage requests
    """
    user = request.user

    StorageResponseFormSet = modelformset_factory(StorageRequest,
        fields=('response', 'response_message'),
        widgets={'response':Select(choices=forms.RESPONSE_CHOICES),
                 'response_message':Textarea()}, extra=0)

    if request.method == 'POST':
        storage_response_formset = StorageResponseFormSet(request.POST)
        process_storage_response(request, storage_response_formset)

    storage_response_formset = StorageResponseFormSet(
        queryset=StorageRequest.objects.filter(is_active=True))

    return render(request, 'console/storage_requests.html', {'user':user,
        'storage_response_formset':storage_response_formset})


@login_required
@user_passes_test(is_admin)
def project_list(request):
    """
    View list of projects
    """
    projects = Project.objects.all()

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
