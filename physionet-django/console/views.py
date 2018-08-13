import pdb

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404
from django.shortcuts import render
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
    """
    List of submissions the editor is responsible for
    """
    submissions = Submission.objects.filter(is_active=True,
        submission_status__in=[3, 4, 6], editor=request.user)

    return render(request, 'console/console_home.html',
        {'submissions':submissions})


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
                body = loader.render_to_string('console/email/assign_editor_notify.html',
                    {'name':project.submitting_author.get_full_name(),
                     'project':submission.project, 'response':response})
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                    [project.submitting_author.email], fail_silently=False)
                messages.success(request, 'The storage request has been {0}.'.format(response))


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
def user_list(request):
    """
    View list of users
    """
    users = User.objects.all()
    return render(request, 'console/user_list.html', {'users':users})


@login_required
@user_passes_test(is_admin)
def submissions(request):
    """
    Submission control panel. Editors are assigned here.
    """
    if request.method == 'POST':
        assign_editor_form = forms.AssignEditorForm(request.POST)
        if assign_editor_form.is_valid():
            submission = assign_editor_form.cleaned_data['submission']
            submission.editor = assign_editor_form.cleaned_data['editor']
            submission.submission_status = 3
            submission.save()
            # Send the notifying email
            subject = 'Editor assigned to project {0}'.format(submission.project.title)
            body = loader.render_to_string('console/email/assign_editor_notify.html',
                {'project':submission.project, 'editor':submission.editor})

            for email in submission.project.get_author_info():
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                    [email], fail_silently=False)
            messages.success(request, 'The editor has been assigned')

    submissions = Submission.objects.filter(is_active=True,
        submission_status__gte=2).order_by('submission_status')
    assign_editor_form = forms.AssignEditorForm()
    n_awaiting_editor = submissions.filter(submission_status=2).count()

    return render(request, 'console/submissions.html',
        {'submissions':submissions, 'assign_editor_form':assign_editor_form,
         'n_awaiting_editor':n_awaiting_editor})


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
        edit_submission_form = forms.EditSubmissionForm(request.POST)
        if edit_submission_form.is_valid() and submission.submission_status == 3:
            # Reject
            if edit_submission_form.cleaned_data['decision'] == 0:
                submission.submission_status = 5
                submission.decision = 0
                submission.editor_comments = edit_submission_form.cleaned_data['comments']
            # Resubmit with changes
            elif edit_submission_form.cleaned_data['decision'] == 1:
                submission.submission_status = 4
                resubmission = Resubmission.objects.create(submission=submission,
                    editor_comments=edit_submission_form.cleaned_data['comments'])
            # Accept
            else:
                submission.submission_status = 6
                submission.decision = 1
                submission.editor_comments = edit_submission_form.cleaned_data['comments']
                # Notify authors of decision
                subject = 'Submission accepted for project {0}'.format(submission.project.title)
                body = loader.render_to_string(
                    'console/email/accept_submission_notify.html',
                    {'project':submission.project, 'domain':get_current_site(request)})
                for email in submission.project.get_author_info():
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                        [email], fail_silently=False)

            submission.save()
            return render(request, 'console/submission_response.html',
                {'response':edit_submission_form.cleaned_data['decision']})

    edit_submission_form = forms.EditSubmissionForm()

    return render(request, 'console/edit_submission.html',
        {'submission':submission, 'edit_submission_form':edit_submission_form})
