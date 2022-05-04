"""
Generate verification tokens for AssociatedEmails that don't have them.

This command is a temporary measure to enable the site to migrate away
from the old insecure AssociatedEmail tokens.

After the server is updated, user.views.add_email will generate a
random token for each new AssociatedEmail, and user.views.verify_email
will require the token supplied by the user to be correct.  At that
time, there will be some AssociatedEmails that have been created
(without a verification_token) and not yet verified.  Those people
will have been sent a message saying something like:

    Subject: PhysioNet Email Verification

    You have requested this email to be added to your account on
    physionet.org. Please verify this email by clicking the following
    activation link, or copying and pasting the link into your web
    browser:

    https://physionet.org/verify/OQ/5ek-ab0712b737f350792636/

and of course this link will not work anymore.

This command will identify those AssociatedEmails which did not have a
verification token set, which were created in the past 3 days, and
which have not yet been verified, and will send a second email saying:

    Subject: PhysioNet Email Verification (CORRECTION)

    You have requested this email to be added to your account on
    physionet.org. Please verify this email by clicking the following
    activation link, or copying and pasting the link into your web
    browser:

    https://physionet.org/verify/OQ/7kArLhMEsShJn98cQzIq/
"""

import datetime
import os

from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode

from user.models import AssociatedEmail


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        now = timezone.now()
        limit = now - datetime.timedelta(
            days=AssociatedEmail.VERIFICATION_TIMEOUT_DAYS)

        associated_emails = AssociatedEmail.objects.filter(
            is_verified=False,
            verification_token=None,
            added_date__gt=limit).order_by('-added_date')

        if options['dry_run']:
            for associated_email in associated_emails:
                print('{}'.format(associated_email.email))
        else:
            for associated_email in associated_emails:
                try:
                    self.update_token(associated_email.pk)
                    print('{}: OK'.format(associated_email.email))
                except Exception as exc:
                    print('{}: FAIL ({})'.format(associated_email.email, exc))

    def update_token(self, associated_email_id):
        with transaction.atomic():
            associated_email = AssociatedEmail.objects.get(
                pk=associated_email_id)
            if associated_email.is_verified:
                return
            if associated_email.verification_token:
                return

            # Generate and save a new verification token
            token = get_random_string(20)
            associated_email.verification_token = token
            associated_email.save()

            user = associated_email.user

            # Send an updated email (this mimics user.views.add_email)

            uidb64 = force_str(urlsafe_base64_encode(force_bytes(associated_email.pk)))
            subject = "PhysioNet Email Verification (CORRECTION)"
            context = {
                'name': user.get_full_name(),
                'domain': 'physionet.org',
                'url_prefix': 'https://physionet.org',
                'uidb64': uidb64,
                'token': token,
                'SITE_NAME': settings.SITE_NAME,
            }
            body = loader.render_to_string('user/email/verify_email_email.html', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                [associated_email.email], fail_silently=False)
