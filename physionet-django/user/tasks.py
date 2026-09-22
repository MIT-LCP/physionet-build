from background_task import background

from user.citi_training_module import verify_training_via_citi_api
from user.models import Training


@background()
def run_citi_api_verification(training_id):
    """
    Run CITI API verification for a training submission.

    This is dispatched as a background task after a CITI-related training
    is submitted. The API results are stored in a CITIVerification record
    for admin review.
    """
    training = Training.objects.get(id=training_id)
    verify_training_via_citi_api(training)
