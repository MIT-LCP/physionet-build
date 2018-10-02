from datetime import datetime, timezone
from django_cron import CronJobBase, Schedule

from user.models import AssociatedEmail
from project.models import Invitation

TIME_LIMIT = 15

class Remove_Unverified_Emails(CronJobBase):
    RUN_EVERY_MINS = 1
    RETRY_AFTER_FAILURE_MINS = 5

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS, 
        retry_after_failure_mins=RETRY_AFTER_FAILURE_MINS)

    code = 'physionet.Remove_Unverified_Emails'

    def do(self):
        users = AssociatedEmail.objects.all()
        for person in users:
            if not person.is_verified:
                dates = datetime.now(timezone.utc) - person.added_date
                if dates.days > TIME_LIMIT:
                    AssociatedEmail.objects.get(id=person.id).delete()
                    print('{0}: Deleted email {1} from user {2}'.format(
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), person.email, 
                        person.user.username))


class Remove_Outstanging_invites(CronJobBase):
    RUN_EVERY_MINS = 1
    RETRY_AFTER_FAILURE_MINS = 5
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS, retry_after_failure_mins=RETRY_AFTER_FAILURE_MINS)

    code = 'physionet.Remove_Outstanging_invites'

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
                    print('{0}: Removed author invitation for project {1} from {2} to {3}'.format(
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), invite.project.title, 
                        invite.inviter.email, invite.email))
