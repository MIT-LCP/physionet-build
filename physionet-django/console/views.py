import pdb

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory, Select, Textarea
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from . import forms
from project.models import Project, StorageRequest, Submission
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

RESPONSE_ACTIONS = {0:'rejected', 1:'accepted'}

def is_admin(user, *args, **kwargs):
    return user.is_admin


# ------------------------- Views begin ------------------------- #

def console_home(request):
    return render(request, 'console/console_home.html')


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
                    project = storage_request.project
                    project.storage_allowance = storage_request.request_allowance
                    project.save()
                messages.success(request, 'The storage request has been %s.' % RESPONSE_ACTIONS[storage_request.response])


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
        widgets={'response':Select(choices=RESPONSE_CHOICES),
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
    Submission control panel
    """
    if request.method == 'POST':
        assign_editor_form = forms.AssignEditorForm(request.POST)
        if assign_editor_form.is_valid():
            submission = assign_editor_form.cleaned_data['submission']
            submission.editor = assign_editor_form.cleaned_data['editor']
            submission.submission_status = 3
            submission.save()
            messages.success(request, 'The editor has been assigned')

    # Submissions awaiting an editor
    submissions = Submission.objects.filter(is_active=True,
        submission_status__gte=2).order_by('submission_status')
    assign_editor_form = forms.AssignEditorForm()

    return render(request, 'console/submissions.html',
        {'submissions':submissions, 'assign_editor_form':assign_editor_form})


@login_required
@user_passes_test(is_admin)
def editor_home(request):
    """
    List of submissions the editor is responsible for
    """
    submissions = Submission.objects.filter(is_active=True, submission_status=3,
        editor=request.user)

    return render(request, 'console/editor_home.html', {'submissions':submissions})


@login_required
@user_passes_test(is_admin)
def edit_submission(request, submission_id):
    """
    Page to respond to a particular submission, as an editor
    """
    submission = Submission.objects.get(id=submission_id)
    # The user must be the editor
    if request.user != submission.editor:
        return Http404()


    return render(request, 'console/edit_submission.html')
