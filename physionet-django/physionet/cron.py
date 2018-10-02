from datetime import datetime, timezone
from django_cron import CronJobBase, Schedule

from django.conf import settings
from django.core.mail import send_mail
from django.template import loader

from user.models import AssociatedEmail
from project.models import Invitation

TIME_LIMIT = 15

class RemoveUnverifiedEmails(CronJobBase):
    RUN_EVERY_MINS = 1
    RETRY_AFTER_FAILURE_MINS = 5

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS, 
        retry_after_failure_mins=RETRY_AFTER_FAILURE_MINS)

    code = 'physionet.RemoveUnverifiedEmails'

    def do(self):
        users = AssociatedEmail.objects.filter(is_primary_email=False)
        for person in users:
            if not person.is_verified:
                dates = datetime.now(timezone.utc) - person.added_date
                if dates.days > TIME_LIMIT:
                    AssociatedEmail.objects.get(id=person.id).delete()
                    print('{0}: Deleted email {1} from user {2}'.format(
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), person.email, 
                        person.user.email))
                    subject = "PhysioNet Unverified Email Removal"
                    context = {'name':person.user.get_full_name(), 'email': person.email}
                    body = loader.render_to_string('user/email/unverified_email_removal.html', context)
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                        [person.user.email], fail_silently=False)

class RemoveOutstandingInvites(CronJobBase):
    RUN_EVERY_MINS = 1
    RETRY_AFTER_FAILURE_MINS = 5
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS, 
        retry_after_failure_mins=RETRY_AFTER_FAILURE_MINS)

    code = 'physionet.RemoveOutstandingInvites'

    def do(self):
        invitations = Invitation.objects.filter(invitation_type='author', is_active=True)
        for invite in invitations:
            if invite.is_active:
                dates = datetime.now(timezone.utc) - invite.request_datetime
                if dates.days > TIME_LIMIT:
                    invite.response_message = "Time limit for outstanding invitation passed."
                    invite.response = False
                    invite.response_datetime = datetime.now(timezone.utc)
                    invite.is_active = False
                    invite.save()
                    subject = "PhysioNet Unconfirmed Author Removal"
                    context = {'name':invite.inviter.get_full_name(), 'email':invite.email,
                        'title':invite.project.title}
                    body = loader.render_to_string('project/email/unconfirmed_author_removal.html', context)
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                        [invite.inviter.email], fail_silently=False)
                    print('{0}: Removed author invitation for project {1} from {2} to {3}'.format(
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), invite.project.title, 
                        invite.inviter.email, invite.email))
