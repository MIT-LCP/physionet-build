import pdb

from django import forms
from django.utils import timezone

from project.models import ActiveProject, SubmissionLog, ResubmissionLog
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

YES_NO = (
    ('', '-----------'),
    (1, 'Yes'),
    (0, 'No')
)


class AssignEditorForm(forms.Form):
    """
    Assign an editor to a project under submission
    """
    project = forms.ModelChoiceField(queryset=ActiveProject.objects.filter(
        submission_status=10))
    editor = forms.ModelChoiceField(queryset=User.objects.filter(
        is_admin=True))


class EditSubmissionForm(forms.ModelForm):
    """
    For an editor to make a decision regarding a submission.
    There is another form for responding to resubmission
    """

    class Meta:
        model = SubmissionLog
        fields = ('well_described', 'data_open_format',
            'data_machine_readable', 'reusable', 'editor_comments', 'decision')
        labels = {'well_described':'The project is well described by the metadata',
            'data_open_format':'The data files are provided in an open format',
            'data_machine_readable':'The data files are machine readable',
            'reusable':'The resource is reusable by other investigators',
            'editor_comments':'Comments to authors'}
        widgets = {'well_described':forms.Select(choices=YES_NO),
            'data_open_format':forms.Select(choices=YES_NO),
            'data_machine_readable':forms.Select(choices=YES_NO),
            'reusable':forms.Select(choices=YES_NO),
            'editor_comments':forms.Textarea(),
            'decision':forms.Select(choices=SUBMISSION_RESPONSE_CHOICES)}

    def __init__(self, resource_type=0, *args, **kwargs):
        """
        Set the choice fields to required
        """
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type
        for f in ['well_described', 'data_open_format', 'data_machine_readable', 'reusable']:
            self.fields[f].required = True

    def clean(self):
        """
        May not accept if the quality assurance fields are not all True
        """
        if self.errors:
            return

        if self.cleaned_data['decision'] != 3:
            for field in :
                if self.cleaned_data[field]:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass before you accept the project')


    def save(self):
        submission = super().save()

        # Reject
        if submission.decision == 1:
            submission.is_active = False

        # Update the submission status to reflect the decision
        submission.status = submission.decision
        submission.decision_datetime = timezone.now()
        submission.save()
        return submission
