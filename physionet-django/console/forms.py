from django import forms

from project.models import Submission
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

SUBMISSION_RESPONSE_CHOICES = (
    (0, 'Reject'),
    (1, 'Resubmit with changes'),
    (2, 'Accept')
)


class AssignEditorForm(forms.Form):
    """
    Assign an editor to a submission
    """
    submission = forms.ModelChoiceField(queryset=Submission.objects.filter(submission_status=2))
    editor = forms.ModelChoiceField(queryset=User.objects.filter(is_admin=True))


class EditSubmissionForm(forms.Form):
    """
    For an editor to make a decision regarding a submission.
    Not a ModelForm because we might need to create a resubmission object
    """

    comments = forms.CharField(widget=forms.Textarea)
    decision = forms.ChoiceField(choices=SUBMISSION_RESPONSE_CHOICES)
