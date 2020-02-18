import re
import pdb

from django import forms
from django.utils import timezone
from django.core.validators import validate_integer, validate_email, URLValidator
from google.cloud import storage
from django.db import transaction
from django.conf import settings

from notification.models import News
from project.models import (ActiveProject, EditLog, CopyeditLog,
    PublishedProject, exists_project_slug, DataAccess)
from project.validators import validate_slug, MAX_PROJECT_SLUG_LENGTH
from user.models import User, CredentialApplication
from console.utility import create_doi_draft

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
            'editor_comments', 'auto_doi', 'decision')

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

        if not settings.DATACITE_PREFIX:
            self.fields['auto_doi'].disabled = True
            self.initial['auto_doi'] = False

        # This will be used in clean
        self.quality_assurance_fields = EditLog.QUALITY_ASSURANCE_FIELDS[resource_type.id]

        rm_fields = set(self.base_fields) - set(self.quality_assurance_fields) - set(EditLog.EDITOR_FIELDS)
        for f in rm_fields:
            del(self.fields[f])

        for (f, lbl) in EditLog.LABELS[resource_type.id].items():
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
        with transaction.atomic():
            edit_log = super().save(commit=False)
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
                project.latest_reminder = now
                project.save()
            # Accept
            else:
                project.submission_status = 40
                project.editor_accept_datetime = now
                project.latest_reminder = now
                if self.cleaned_data['auto_doi'] and not project.doi:
                    project.doi = create_doi_draft(project)
                    if not project.core_project.doi:
                        project.core_project.doi = create_doi_draft(project)
                        project.core_project.save()
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
        with transaction.atomic():
            copyedit_log = super().save(commit=False)
            project = copyedit_log.project
            now = timezone.now()
            copyedit_log.complete_datetime = now
            project.submission_status = 50
            project.copyedit_completion_datetime = now
            project.latest_reminder = now
            copyedit_log.save()
            project.save()
            return copyedit_log


class PublishForm(forms.Form):
    """
    Form for publishing a project
    """
    slug = forms.CharField(max_length=MAX_PROJECT_SLUG_LENGTH,
                           validators=[validate_slug])
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
            'responder_comments':'Comments (required for rejected applications)',
            'status':'Decision',
        }
        # widgets = {
        #     'responder_comments':forms.Textarea(attrs={'rows': 3}),
        # }

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responder = responder
        self.fields['status'].choices = CredentialApplication.REJECT_ACCEPT_WITHDRAW[:3]

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['status'] == 1 and not self.cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject, you must explain why.')

    def save(self):
        application = super().save()

        if application.status == 1:
            application.reject(self.responder)
        elif application.status == 2:
            application.accept(self.responder)
        elif application.status == 3:
            application.withdraw(self.responder)
        else:
            raise forms.ValidationError('Application status not valid.')

        return application


class AlterCommentsCredentialForm(forms.ModelForm):
    """
    Change the response comments on a processed application
    """
    class Meta:
        model = CredentialApplication
        fields = ('responder_comments',)
        labels = {
            'responder_comments': 'Comments',
        }


class NewsForm(forms.ModelForm):
    """
    To add and edit news items
    """
    project = forms.ModelChoiceField(queryset=PublishedProject.objects.order_by('title'), required=False)

    class Meta:
        model = News
        fields = ('title', 'content', 'url', 'project', 'front_page_banner')


class FeaturedForm(forms.Form):
    """
    To add featured projects
    """
    title = forms.CharField(max_length=50, required=False, label='Title')


class DataAccessForm(forms.ModelForm):
    """
    To add all of the forms to access the data for a project.
    """
    class Meta:
        model = DataAccess
        fields = ('platform', 'location')
        help_texts = {
            'platform': 'Form to access the data.',
            'location': """URL for aws-open-data:<br> https://URL<br><br>
                           Bucket name for aws-s3:<br> s3://BUCKET_NAME<br><br>
                           Organizational Google Group managing access for gcp-bucket:<br> EMAIL@ORGANIZATION<br><br>
                           Organizational Google Group managing access for gcp-bigquery:<br> EMAIL@ORGANIZATION""",
            }

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean_location(self):
        platform = self.cleaned_data['platform']
        location = self.cleaned_data['location']
        if platform == 1:
            validate = URLValidator()
            validate(location)
        elif platform == 2:
            bucket = location.split('s3://')
            if len(bucket) != 2 or bucket[0] != '':
                raise forms.ValidationError('The AWS Bucket name is not valid')
            if not re.fullmatch(r'[\da-z][\da-z-.]+[\da-z]', bucket[1]):
                raise forms.ValidationError('The AWS Bucket name is not valid')
        elif platform in [3, 4]:
            validate_email(location)
        return location

    def save(self):
        data_access = super(DataAccessForm, self).save(commit=False)
        data_access.project = self.project
        data_access.save()
        return data_access
