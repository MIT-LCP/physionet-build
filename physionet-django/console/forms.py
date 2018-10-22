import pdb

from django import forms
from django.utils import timezone

from project.models import ActiveProject, EditLog, CopyeditLog
from user.models import User


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

SUBMISSION_RESPONSE_CHOICES = (
    ('', '-----------'),
    (2, 'Accept'),
    (1, 'Resubmit with changes'),
    (0, 'Reject'),
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
    """
    # Quality assurance fields for data
    DATA_FIELDS = ('soundly_produced', 'well_described', 'open_format',
        'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable')
    SOFTWARE_FIELDS = ()

    class Meta:
        # Populated with fields and labels for both data and software
        # fields. The __init__ function removes unnecessary fields and
        # renames fields
        model = EditLog
        fields = ('soundly_produced', 'well_described', 'open_format',
            'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable',
            'editor_comments', 'decision')
        labels = {
            'soundly_produced':'The data is produced in a sound manner',
            'well_described':'The data is adequately described',
            'open_format':'The data files are provided in an open format',
            'data_machine_readable':'The data files are machine readable',
            'reusable':'All the information needed for reuse is present',
            'no_phi':'No protected health information is contained',
            'pn_suitable':'The content is suitable for PhysioNet',
            'editor_comments':'Comments to authors',
        }
        widgets = {
            'soundly_produced':forms.Select(choices=YES_NO),
            'well_described':forms.Select(choices=YES_NO),
            'open_format':forms.Select(choices=YES_NO),
            'data_machine_readable':forms.Select(choices=YES_NO),
            'reusable':forms.Select(choices=YES_NO),
            'no_phi':forms.Select(choices=YES_NO),
            'pn_suitable':forms.Select(choices=YES_NO),
            'editor_comments':forms.Textarea(),
            'decision':forms.Select(choices=SUBMISSION_RESPONSE_CHOICES)
        }

    def __init__(self, resource_type=0, *args, **kwargs):
        """
        Set the appropriate fields for the given resource type, and
        set the choice fields to required.
        """
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type
        if resource_type == 0:
            for f in set(self.__class__.SOFTWARE_FIELDS) - set(self.__class__.DATA_FIELDS):
                del(self.fields[f])
            for f in self.__class__.DATA_FIELDS:
                self.fields[f].required = True

        elif resource_type == 1:
            for f in set(SOFTWARE_FIELDS) - set(DATA_FIELDS):
                del(self.fields[f])
            for f in DATA_FIELDS:
                self.fields[f].required = True

    def clean(self):
        """
        May not accept if the quality assurance fields are not all True
        """
        if self.errors:
            return

        if self.cleaned_data['decision'] != 3:
            for field in self.__class__.DATA_FIELDS:
                if not self.cleaned_data[field]:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass before you accept the project')

    def save(self):
        """
        Process the editor decision
        """
        edit_log = super().save()
        project = edit_log.project
        now = timezone.now()

        # Reject
        if edit_log.decision == 0:
            pass
        # Resubmit with revisions
        elif edit_log.decision == 1:
            pass
        # Accept
        else:
            project.submission_status = 40
            project.editor_accept_datetime = now
            CopyeditLog.objects.create(project=project)

        project.save()
        edit_log.decision_datetime = now
        edit_log.save()
        return edit_log


class CopyeditForm(forms.ModelForm):
    """
    Submit form to complete copyedit
    """
    class Meta:
        model = CopyeditLog
        fields = ('made_changes', 'changelog_summary')
        widgets = {
            'made_changes':forms.Select(choices=YES_NO),
            'changelog_summary':forms.Textarea()
        }

    def clean(self):
        if self.errors:
            return
        if self.cleaned_data['made_changes'] and not self.cleaned_data['changelog_summary']:
            raise forms.ValidationError('Describe the changes you made.')
        if not self.cleaned_data['made_changes'] and self.cleaned_data['changelog_summary']:
            raise forms.ValidationError('If you describe changes, you must state that changes were made.')

    def save(self):
        """
        Complete the copyedit
        """
        copyedit_log = super().save()
        project = copyedit_log.project
        now = timezone.now()
        copyedit_log.complete_datetime = now
        copyedit_log.save()
        project.submission_status = 50
        project.copyedit_completion_datetime = now
        project.save()
        return copyedit_log
