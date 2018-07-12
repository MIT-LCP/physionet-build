import pdb

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory, Select, Textarea
from django.shortcuts import render
from django.utils import timezone

from project.models import StorageRequest


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
