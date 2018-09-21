import pdb

from django import forms
from django.utils import timezone

from project.models import Submission, Resubmission
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

SUBMISSION_RESPONSE_CHOICES = (
    ('', '-----------'),
    (3, 'Accept'),
    (2, 'Resubmit with changes'),
    (1, 'Reject'),
)


class AssignEditorForm(forms.Form):
    """
    Assign an editor to a submission
    """
    submission = forms.ModelChoiceField(queryset=Submission.objects.filter(
        submission_status=0, editor=None))
    editor = forms.ModelChoiceField(queryset=User.objects.filter(is_admin=True))


class EditSubmissionForm(forms.ModelForm):
    """
    For an editor to make a decision regarding a submission.
    There is another form for responding to resubmission
    """

    class Meta:
        model = Submission
        fields = ('editor_comments', 'decision',)
        widgets= {'editor_comments':forms.Textarea(),
                  'decision':forms.Select(choices=SUBMISSION_RESPONSE_CHOICES)}

    def clean(self):
        """
        The submission must be awaiting an editor response
        """
        cleaned_data = super().clean()

        if self.instance.submission_status != 0:
            raise forms.ValidationError(
                'Unable to edit this submission')

        return cleaned_data

    def save(self):
        submission = super().save()

        # Reject
        if submission.decision == 1:
            submission.is_active = False

        # Update the submission status to reflect the decision
        submission.submission_status = submission.decision
        submission.decision_datetime = timezone.now()
        submission.save()
        return submission

