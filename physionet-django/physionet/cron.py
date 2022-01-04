from django_cron import CronJobBase, Schedule
from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils import timezone

from user.models import AssociatedEmail
from project.models import AuthorInvitation


UNVERIFIED_DAY_LIMIT = 15


class RemoveUnverifiedEmails(CronJobBase):
    RUN_EVERY_MINS = 1
    RETRY_AFTER_FAILURE_MINS = 5

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS,
        retry_after_failure_mins=RETRY_AFTER_FAILURE_MINS)

    code = 'physionet.RemoveUnverifiedEmails'

    def do(self):
        associated_emails = AssociatedEmail.objects.filter(
            is_primary_email=False, is_verified=False,
            added_date__lt=timezone.now() - timezone.timedelta(
                days=UNVERIFIED_DAY_LIMIT))

        for ae in associated_emails:
            ae.delete()
            print('{}: Deleted email {} from user {}'.format(
                timezone.now().strftime('%Y-%m-%d %H:%M:%S'), ae.email,
                ae.user.email))
            subject = "PhysioNet Unverified Email Removal"
            context = {
                'name': ae.user.get_full_name(),
                'email': ae.email,
                'SITE_NAME': settings.SITE_NAME,
            }
            body = loader.render_to_string(
                'user/email/unverified_email_removal.html', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                [ae.user.email], fail_silently=False)


class RemoveOutstandingInvites(CronJobBase):
    RUN_EVERY_MINS = 1
    RETRY_AFTER_FAILURE_MINS = 5
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS,
        retry_after_failure_mins=RETRY_AFTER_FAILURE_MINS)

    code = 'physionet.RemoveOutstandingInvites'

    def do(self):
        invitations = AuthorInvitation.objects.filter(is_active=True,
            request_datetime__lt=timezone.now() - timezone.timedelta(
                days=UNVERIFIED_DAY_LIMIT))

        for invitation in invitations:
            invitation.response_datetime = timezone.now()
            invitation.is_active = False
            invitation.save()
            subject = 'PhysioNet Expired Author Invitation'
            context = {'name':invitation.inviter.get_full_name(),
                'email':invitation.email, 'title':invitation.project.title}
            body = loader.render_to_string(
                'project/email/outstanding_invitation_removal.html', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                [invitation.inviter.email], fail_silently=False)
            print('{}: Removed author invitation for project {} from {} to {}'.format(
                timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                invitation.project.title, invitation.inviter.email,
                invitation.email))
