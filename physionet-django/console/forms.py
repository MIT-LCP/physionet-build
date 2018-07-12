from django import forms

from project.models import Submission
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)


class AssignEditorForm(forms.Form):
    """
    Assign an editor to a submission
    """
    submission = forms.ModelChoiceField(queryset=Submission.objects.filter(submission_status=2))
    editor = forms.ModelChoiceField(queryset=User.objects.filter(is_admin=True))


class EditSubmissionForm(forms.Form):
    """
    For an editor to make a decision regarding a submission
    """
    decision = forms.ChoiceField(choices=RESPONSE_CHOICES)
