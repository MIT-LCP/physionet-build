import re
import pdb

from django import forms
from django.utils import timezone
from django.core.validators import validate_integer

from notification.models import News
from project.models import (ActiveProject, EditLog, CopyeditLog,
    PublishedProject, exists_project_slug)
from user.models import User, CredentialApplication

RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

SUBMISSION_RESPONSE_CHOICES = (
    ('', '-----------'),
    (2, 'Accept'),
    (1, 'Resubmit with revisions'),
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
    project = forms.IntegerField(widget = forms.HiddenInput())
    editor = forms.ModelChoiceField(queryset=User.objects.filter(
        is_admin=True))

    def clean_project(self):
        pid = self.cleaned_data['project']
        validate_integer(pid)
        if ActiveProject.objects.get(id=pid) not in ActiveProject.objects.filter(submission_status=10):
            raise forms.ValidationError('Incorrect project selected.')
        return pid

class EditSubmissionForm(forms.ModelForm):
    """
    For an editor to make a decision regarding a submission.
    Fields are specified for each resource type

    The labels are stored in the model because it requires them to
    render results without using this form
    """
    class Meta:
        # Populated with fields and labels for both data and software
        # fields. The __init__ function removes unnecessary fields and
        # renames fields
        model = EditLog
        fields = ('soundly_produced', 'well_described', 'open_format',
            'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable',
            'editor_comments', 'decision')

        labels = EditLog.COMMON_LABELS

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

    def __init__(self, resource_type, *args, **kwargs):
        """
        Set the appropriate fields/labels for the given resource type,
        and make them required. Remove irrelevant fields.
        """
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type

        # This will be used in clean
        self.quality_assurance_fields = EditLog.QUALITY_ASSURANCE_FIELDS[resource_type]

        rm_fields = set(self.base_fields) - set(self.quality_assurance_fields) - set(EditLog.EDITOR_FIELDS)
        for f in rm_fields:
            del(self.fields[f])

        for l in EditLog.LABELS[resource_type]:
            self.fields[l].label = EditLog.LABELS[resource_type][l]

        # Enforce the requirement of quality assurance fields
        for f in self.quality_assurance_fields:
            self.fields[f].required = True

    def clean(self):
        """
        May not accept if the quality assurance fields are not all True
        """
        if self.errors:
            return

        if self.cleaned_data['decision'] == 2:
            for field in self.quality_assurance_fields:
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
        # This object has to be saved first before calling reject, which
        # edits the related EditLog objects (this).
        edit_log.decision_datetime = now
        edit_log.save()
        # Reject
        if edit_log.decision == 0:
            project.reject()
            # Have to reload this object which is changed by the reject
            # function
            edit_log = EditLog.objects.get(id=edit_log.id)
        # Resubmit with revisions
        elif edit_log.decision == 1:
            project.submission_status = 30
            project.revision_request_datetime = now
            project.save()
        # Accept
        else:
            project.submission_status = 40
            project.editor_accept_datetime = now
            CopyeditLog.objects.create(project=project)
            project.save()
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


class PublishForm(forms.Form):
    """
    Form for publishing a project
    """
    slug = forms.CharField(max_length=20)
    doi = forms.CharField(max_length=50, label='DOI')
    make_zip = forms.ChoiceField(choices=YES_NO, label='Make zip of all files')

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields['slug'].initial = project.slug

    def clean_slug(self):
        """
        Ensure that the slug is valid and not taken.
        """
        data = self.cleaned_data['slug']
        if data != self.project.slug:
            if exists_project_slug(data):
                raise forms.ValidationError('The slug is already taken by another project.')

        if not re.fullmatch(r'[a-zA-Z\d\-]{1,20}', data):
            raise forms.ValidationError('Must only contain alphanumerics and hyphens with length 1-20.')

        return data

    def clean_doi(self):
        data = self.cleaned_data['doi']
        if PublishedProject.objects.filter(doi=data):
            raise forms.ValidationError('Published project with DOI already exists.')
        return data


class DOIForm(forms.ModelForm):
    """
    Form to edit the doi of a published project
    """
    class Meta:
        model = PublishedProject
        fields = ('doi',)
        labels = {'doi':'DOI'}

    def clean_doi(self):
        data = self.cleaned_data['doi']
        if PublishedProject.objects.filter(doi=data).exclude(id=self.instance.id):
            raise forms.ValidationError('Published project with DOI already exists.')
        return data


class ProcessCredentialForm(forms.ModelForm):
    """
    Form to respond to a credential application
    """

    class Meta:
        model = CredentialApplication
        fields = ('responder_comments', 'status')
        labels = {
            'responder_comments':'Comments (for rejections)',
            'status':'Decision',
        }
        widgets = {
            'responder_comments':forms.Textarea(),
        }

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responder = responder

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['status'] == 1 and not self.cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject, you must describe why.')

    def save(self):
        application = super().save()
        now = timezone.now()

        if application.status == 2:
            user = application.user
            user.is_credentialed = True
            user.credential_datetime = now
            user.save()

        application.responder = self.responder
        application.decision_datetime = timezone.now()
        application.save()
        return application


class NewsForm(forms.ModelForm):
    """
    To add and edit news items
    """
    class Meta:
        model = News
        fields = ('title', 'content', 'url')

# class AddAffiliateForm(forms.Form):
#     """
#     Add a user to the list of LCP affiliates

#     """
#     username = forms.CharField(max_length=50)

#     def clean_username(self):
#         data = self.cleaned_data['username']
#         user = User.objects.filter(username=data)
#         if user:
#             user = user.get()
#             if user.lcp_affiliated:
#                 raise forms.ValidationError('User is already LCP affiliated')
#             else:
#                 self.user = user
#         else:
#             raise forms.ValidationError('User does not exist')
#         return data

# class RemoveAffiliateForm(forms.Form):
#     """
#     Remove a user from the list of LCP affiliates
#     """
#     user = forms.ModelChoiceField(queryset=User.objects.filter(
#         lcp_affiliated=True))
