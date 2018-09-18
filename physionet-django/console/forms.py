import pdb

from django import forms

from project.models import Submission, Resubmission
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

SUBMISSION_RESPONSE_CHOICES = (
    ('', '-----------'),
    (3, 'Accept'),
    (1, 'Reject'),
    (2, 'Resubmit with changes')
)


class AssignEditorForm(forms.Form):
    """
    Assign an editor to a submission
    """
    submission = forms.ModelChoiceField(queryset=Submission.objects.filter(
        submission_status=2))
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

    def __init__(self, include_blank=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Include a blank option, even though it is a required field, in
        # case the editor accidentally submits
        if not include_blank:
            self.fields['decision'].choices = (s for s in SUBMISSION_RESPONSE_CHOICES[2:])
            pdb.set_trace()

    def clean(self):
        """
        The submission must be awaiting an editor response
        """
        cleaned_data = super().clean()

        if self.instance.submission_status not in [3, 4]:
            raise forms.ValidationError(
                'Submission is not awaiting an editor response')

        return cleaned_data

    def save(self):
        submission = super().save()

        # Resubmit
        if submission.decision == 1:
            Resubmission.objects.create(submission=submission)
        # Reject or accept
        elif submission.decision in [2, 3]:
            submission.is_active = False

        # Update the submission status to reflect the decision
        submission.submission_status = submission.decision + 3
        submission.save()
        return submission

