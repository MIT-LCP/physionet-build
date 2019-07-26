import re
import pdb

from django import forms
from django.utils import timezone
from django.core.validators import validate_integer

from notification.models import News
from project.models import (ActiveProject, EditLog, CopyeditLog,
    PublishedProject, exists_project_slug)
from project.validators import validate_slug
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

# See also RESPONSE_LABEL in project/models.py
YES_NO_UNDETERMINED = (
    ('', '-----------'),
    (1, 'Yes'),
    (0, 'No'),
    (None, 'Undetermined')
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
            'soundly_produced': forms.Select(choices=YES_NO_UNDETERMINED),
            'well_described': forms.Select(choices=YES_NO_UNDETERMINED),
            'open_format': forms.Select(choices=YES_NO_UNDETERMINED),
            'data_machine_readable': forms.Select(choices=YES_NO_UNDETERMINED),
            'reusable': forms.Select(choices=YES_NO_UNDETERMINED),
            'no_phi': forms.Select(choices=YES_NO_UNDETERMINED),
            'pn_suitable': forms.Select(choices=YES_NO_UNDETERMINED),
            'editor_comments': forms.Textarea(),
            'decision': forms.Select(choices=SUBMISSION_RESPONSE_CHOICES)
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

        for (f, lbl) in EditLog.LABELS[resource_type].items():
            hints = EditLog.HINTS.get(f)
            if hints:
                lbl += '<ul><li>' + '</li><li>'.join(hints) + '</li></ul>'
            self.fields[f].label = lbl

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
    slug = forms.CharField(max_length=20, validators=[validate_slug])
    doi = forms.CharField(max_length=50, label='DOI', required=False)
    make_zip = forms.ChoiceField(choices=YES_NO, label='Make zip of all files')

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        # No option to set slug if publishing new version
        if self.project.version_order:
            del(self.fields['slug'])
        else:
            self.fields['slug'].initial = project.slug

    def clean_slug(self):
        """
        Ensure that the slug is valid and not taken.
        """
        data = self.cleaned_data['slug']
        if data != self.project.slug:
            if exists_project_slug(data):
                raise forms.ValidationError('The slug is already taken by another project.')

        return data

    def clean_doi(self):
        data = self.cleaned_data['doi']
        # Temporary workaround
        # if PublishedProject.objects.filter(doi=data):
        #     raise forms.ValidationError('Published project with DOI already exists.')
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


class TopicForm(forms.Form):
    """
    Form to set tags for a published project
    """
    topics = forms.CharField(required=False, max_length=800,
        label='Comma delimited topics')

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def set_initial(self):
        """
        Set the initial topics char field from the project's existing
        topics.
        """
        self.fields['topics'].initial = ','.join(
            t.description for t in self.project.topics.all())

    def clean_topics(self):
        data = self.cleaned_data['topics']
        # It is allowed to be blank, but not have multiple items
        # that include a blank
        if data == '':
            return data

        topics = [x.strip() for x in data.split(',')]

        if len(topics) != len(set(topics)):
            raise forms.ValidationError('Topics must be unique')

        for t in topics:
            if not re.fullmatch(r'[\w][\w\ -]*', t):
                raise forms.ValidationError('Each topic must contain letters, '
                    'numbers, spaces, underscores, and hyphens only, and '
                    'begin with a letter or number.')

        self.topic_descriptions = [t.lower() for t in topics]
        return data


class DeprecateFilesForm(forms.Form):
    """
    For deprecating a project's files
    """
    delete_files = forms.ChoiceField(choices=YES_NO)


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
        # widgets = {
        #     'responder_comments':forms.Textarea(attrs={'rows': 3}),
        # }

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
        fields = ('title', 'content', 'url', 'project')
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created_by = user

    def save(self):
        news = super().save(commit=False)
        news.created_by = self.created_by
        news.save()
        return news

class FeaturedForm(forms.Form):
    """
    To add featured projects
    """
    title = forms.CharField(max_length=50, required=False, label='Title')
