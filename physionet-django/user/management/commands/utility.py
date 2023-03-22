import logging

from django.utils import timezone

from user.models import CredentialApplication


def get_credential_awaiting_reference(n, days, ignore_reminded_application=False):
    """
    Get n CredentialApplication that has been pending reference response for more than the given days.
    """
    today = timezone.now()
    limit = today - timezone.timedelta(days=days)

    pending_applications = CredentialApplication.objects.filter(status=CredentialApplication.Status.PENDING,
                                                                credential_review__status=30)
    if ignore_reminded_application:
        pending_applications = pending_applications.filter(reference_reminder_datetime__isnull=True)
    # finally get applications that have been pending for more than the limit
    filtered_applications = pending_applications.filter(reference_contact_datetime__lt=limit)[:n]
    return filtered_applications
