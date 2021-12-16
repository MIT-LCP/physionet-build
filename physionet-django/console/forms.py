import pdb
import re

from django.forms.widgets import RadioSelect

from console.utility import generate_doi_payload, register_doi
from dal import autocomplete
from django import forms
from django.conf import settings
from django.core.validators import URLValidator, validate_email, validate_integer
from django.db import transaction
from django.utils import timezone
from google.cloud import storage
from notification.models import News
from physionet.models import Section
from project.models import (
    ActiveProject,
    Contact,
    CopyeditLog,
    DataAccess,
    EditLog,
    PublishedAffiliation,
    PublishedAuthor,
    PublishedProject,
    exists_project_slug,
)
from project.projectfiles import ProjectFiles
from project.validators import MAX_PROJECT_SLUG_LENGTH, validate_doi, validate_slug
from user.models import CredentialApplication, CredentialReview, User, TrainingQuestion

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

REVIEW_RESPONSE_CHOICES = (
    (1, 'Pass to Next Stage'),
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

YES_NO_UNDETERMINED_REVIEW = (
    (True, 'Yes'),
    (False, 'No'),
    (None, 'Undetermined'),
)

YES_NO_NA_UNDETERMINED = (
    (1, 'Yes'),
    (0, 'No'),
    (None, 'N/A or Undetermined')
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


class ReassignEditorForm(forms.Form):
    """
    Assign an editor to a project under submission
    """
    editor = forms.ModelChoiceField(queryset=User.objects.filter(
        is_admin=True), widget=forms.Select(attrs={'onchange': 'set_editor_text()'}))

    def __init__(self, user, *args, **kwargs):
        """
        Set the appropriate queryset
        """
        super().__init__(*args, **kwargs)
        self.fields['editor'].queryset = self.fields['editor'].queryset.exclude(
            username=user.username)


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
        fields = (
            'soundly_produced',
            'well_described',
            'open_format',
            'data_machine_readable',
            'reusable',
            'no_phi',
            'pn_suitable',
            'ethics_included',
            'editor_comments',
            'auto_doi',
            'decision',
        )

        labels = EditLog.COMMON_LABELS

        auto_doi = forms.BooleanField(required=False, initial=True)

        widgets = {
            'soundly_produced': forms.Select(choices=YES_NO_UNDETERMINED),
            'well_described': forms.Select(choices=YES_NO_UNDETERMINED),
            'open_format': forms.Select(choices=YES_NO_UNDETERMINED),
            'data_machine_readable': forms.Select(choices=YES_NO_UNDETERMINED),
            'reusable': forms.Select(choices=YES_NO_UNDETERMINED),
            'no_phi': forms.Select(choices=YES_NO_UNDETERMINED),
            'pn_suitable': forms.Select(choices=YES_NO_UNDETERMINED),
            'editor_comments': forms.Textarea(),
            'decision': forms.Select(choices=SUBMISSION_RESPONSE_CHOICES),
            'ethics_included': forms.Select(choices=YES_NO_UNDETERMINED),
            'auto_doi': forms.HiddenInput(),
        }

    def __init__(self, resource_type, *args, **kwargs):
        """
        Set the appropriate fields/labels for the given resource type,
        and make them required. Remove irrelevant fields.
        """
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type

        self.fields['auto_doi'].disabled = True

        if not settings.DATACITE_PREFIX:
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

                CopyeditLog.objects.create(project=project)
                project.save()

                if self.cleaned_data['auto_doi']:
                    # register draft DOIs
                    if not project.doi:
                        payload = generate_doi_payload(project, event="draft")
                        register_doi(payload, project)
                    if not project.core_project.doi:
                        payload = generate_doi_payload(project, event="draft",
                                                       core_project=True)
                        register_doi(payload, project.core_project)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['made_changes'].required = True

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
            project.create_license_file()
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

        if not ProjectFiles().can_make_zip():
            self.fields['make_zip'].disabled = True
            self.fields['make_zip'].required = False
            self.fields['make_zip'].initial = 0

    def clean_slug(self):
        """
        Ensure that the slug is valid and not taken.
        """
        data = self.cleaned_data['slug']
        if data != self.project.slug:
            if exists_project_slug(data):
                raise forms.ValidationError('The slug is already taken by another project.')
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


class ContactCredentialRefForm(forms.Form):
    """
    Contact the reference for a credentialing application.
    """
    subject = forms.CharField(required=True)
    body = forms.CharField(widget=forms.Textarea)


class ProcessCredentialForm(forms.ModelForm):
    """
    Form to respond to a credential application
    """

    class Meta:
        model = CredentialApplication
        fields = ('responder_comments', 'status')
        labels = {
            'responder_comments':'Comments (required for rejected applications). This will be sent to the applicant.',
            'status':'Decision',
        }
        # widgets = {
        #     'responder_comments': forms.Textarea(attrs={'rows': 5}),
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


class ProcessCredentialReviewForm(forms.ModelForm):
    """
    Form to respond to a credential application review
    """

    class Meta:
        model = CredentialApplication
        fields = ('responder_comments', 'status')
        labels = {
            'responder_comments':'Comments (required for rejected applications). This will be sent to the applicant.',
            'status':'Decision',
        }
        widgets = {
            'responder_comments': forms.Textarea(attrs={'rows': 5}),
        }

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


class InitialCredentialForm(forms.ModelForm):
    """
    Form to respond to a credential application in the initial review stage
    """

    decision = forms.ChoiceField(choices=REVIEW_RESPONSE_CHOICES,
            widget=forms.RadioSelect)

    class Meta:
        model = CredentialReview
        fields = ('fields_complete', 'appears_correct', 'lang_understandable',
                  'responder_comments', 'decision')

        labels = {
            'fields_complete': 'Are all of the required fields complete?',
            'appears_correct': 'Does the application clearly avoid frivolous text such as "aa"?',
            'lang_understandable': 'Is any non-English text (e.g. job titles) easily translated?',
            'responder_comments': 'Comments (required for rejected applications). This will be sent to the applicant.',
            'decision': 'Decision',
        }

        widgets = {
            'fields_complete': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'appears_correct': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'lang_understandable': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'responder_comments': forms.Textarea(attrs={'rows': 5}),
            'decision': forms.RadioSelect(choices=REVIEW_RESPONSE_CHOICES)
        }

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # This will be used in clean
        self.quality_assurance_fields = ('fields_complete', 'appears_correct',
                                         'lang_understandable')

        self.responder = responder
        self.fields['decision'].choices = REVIEW_RESPONSE_CHOICES

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['decision'] == '1':
            for field in self.quality_assurance_fields:
                if not self.cleaned_data[field]:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass '
                          'before you approve the application')

        if self.cleaned_data['decision'] == '0' and not self.cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject, you must explain why.')

    def save(self):
        application = super().save()
        if self.cleaned_data['decision'] == '0':
            application.reject(self.responder)
        elif self.cleaned_data['decision'] == '1':
            application.update_review_status(20)
        else:
            raise forms.ValidationError('Application status not valid.')

        return application


class PersonalCredentialForm(forms.ModelForm):
    """
    Form to respond to a credential application in the ID check stage
    """

    decision = forms.ChoiceField(choices=REVIEW_RESPONSE_CHOICES,
            widget=forms.RadioSelect)

    class Meta:
        model = CredentialReview
        fields = ('user_searchable', 'user_has_papers',
                  'research_summary_clear', 'course_name_provided', 'user_understands_privacy',
                  'user_org_known', 'user_details_consistent',
                  'responder_comments', 'decision')

        labels = {
            'user_searchable': 'Do you find search results for the applicant\'s name (possibly include their organization in the search query)?',
            'user_has_papers': 'Can you find publications linked to the applicant (possibly include the reference in the search query)?',
            'research_summary_clear': 'Is the research summary sufficiently descriptive?',
            'course_name_provided': 'If applicable, does the research summary include course name and number?',
            'user_understands_privacy': 'Does the research summary indicate an understanding that data must not be shared (e.g. no plural pronouns such as "we", "us", etc.)?',
            'user_org_known': 'Does the organization have a website or other online presence (*not* "MIT Affiliates")?',
            'user_details_consistent': 'Is the information consistent (independent researcher should not list an organization, obvious students should be listed as either "student" or "postdoc", MD\'s with a hospital as their organization should be "hospital researcher", the county and state mismatches, etc.)?',
            'responder_comments': 'Comments (required for rejected applications). This will be sent to the applicant.',
            'decision': 'Decision',
        }

        widgets = {
            'user_searchable': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'user_has_papers': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'research_summary_clear': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'course_name_provided': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'user_understands_privacy': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'user_org_known': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'user_details_consistent': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'responder_comments': forms.Textarea(attrs={'rows': 5}),
            'decision': forms.RadioSelect(choices=REVIEW_RESPONSE_CHOICES)
        }

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # This will be used in clean
        self.quality_assurance_fields = ('research_summary_clear', 'user_understands_privacy', 'user_org_known', 'user_details_consistent')
        self.categorical_fields = ('user_searchable', 'user_has_papers', 'course_name_provided')

        self.responder = responder
        self.fields['decision'].choices = REVIEW_RESPONSE_CHOICES

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['decision'] == '1':
            for field in self.quality_assurance_fields:
                if not self.cleaned_data[field]:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass '
                          'before you approve the application')
            for field in self.categorical_fields:
                if self.cleaned_data[field] is False:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass '
                          'before you approve the application')

        if self.cleaned_data['decision'] == '0' and not self.cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject, you must explain why.')

    def save(self):
        application = super().save()
        if self.cleaned_data['decision'] == '0':
            application.reject(self.responder)
        elif self.cleaned_data['decision'] == '1':
            application.update_review_status(30)
        else:
            raise forms.ValidationError('Application status not valid.')

        return application


class ReferenceCredentialForm(forms.ModelForm):
    """
    Form to respond to a credential application in the reference check stage
    """

    decision = forms.ChoiceField(choices=REVIEW_RESPONSE_CHOICES,
            widget=forms.RadioSelect)

    class Meta:
        model = CredentialReview
        fields = ('ref_appropriate', 'ref_searchable', 'ref_has_papers',
                  'ref_is_supervisor', 'ref_course_list',
                  'responder_comments', 'decision')

        labels = {
            'ref_appropriate': 'Is the reference appropriate?',
            'ref_searchable': 'Is the reference easily searchable?',
            'ref_has_papers': 'Can you find publications linked to the reference?',
            'ref_is_supervisor': 'If applicable (for students and postdocs only), is the reference in a supervisory position?',
            'ref_course_list': 'If applicable (for students and postdocs only), is the applicant included in a list of course participants?',
            'responder_comments': 'Comments (required for rejected applications). This will be sent to the applicant.',
            'decision': 'Decision',
        }

        widgets = {
            'ref_appropriate': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'ref_searchable': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'ref_has_papers': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'ref_is_supervisor': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'ref_course_list': forms.RadioSelect(choices=YES_NO_NA_UNDETERMINED),
            'responder_comments': forms.Textarea(attrs={'rows': 5}),
            'decision': forms.RadioSelect(choices=REVIEW_RESPONSE_CHOICES)
        }

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # This will be used in clean
        self.quality_assurance_fields = ('ref_appropriate',)
        self.categorical_fields = ('ref_searchable', 'ref_has_papers', 'ref_is_supervisor', 'ref_course_list')

        self.responder = responder
        self.fields['decision'].choices = REVIEW_RESPONSE_CHOICES

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['decision'] == '1':
            for field in self.quality_assurance_fields:
                if not self.cleaned_data[field]:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass '
                          'before you approve the application')
            for field in self.categorical_fields:
                if self.cleaned_data[field] is False:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass '
                          'before you approve the application')

        if self.cleaned_data['decision'] == '0' and not self.cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject, you must explain why.')

    def save(self):
        application = super().save()
        if self.cleaned_data['decision'] == '0':
            application.reject(self.responder)
        elif self.cleaned_data['decision'] == '1':
            application.update_review_status(40)
        else:
            raise forms.ValidationError('Application status not valid.')

        return application


class ResponseCredentialForm(forms.ModelForm):
    """
    Form to respond to a credential application in the reference response
    check stage
    """

    decision = forms.ChoiceField(choices=REVIEW_RESPONSE_CHOICES,
            widget=forms.RadioSelect)

    class Meta:
        model = CredentialReview
        fields = ('ref_knows_applicant', 'ref_approves',
                  'ref_understands_privacy', 'responder_comments', 'decision')

        labels = {
            'ref_knows_applicant': 'Does the reference know the applicant?',
            'ref_approves': 'Does the reference approve the applicant for use of restricted data?',
            'ref_understands_privacy': 'Does the response indicate an understanding that data must not be shared (e.g. no plural pronouns such as "we", "us", etc.)?',
            'responder_comments': 'Comments (required for rejected applications). This will be sent to the applicant.',
            'decision': 'Decision',
        }

        widgets = {
            'ref_knows_applicant': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'ref_approves': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'ref_understands_privacy': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW),
            'responder_comments': forms.Textarea(attrs={'rows': 5}),
            'decision': forms.RadioSelect(choices=REVIEW_RESPONSE_CHOICES)
        }

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # This will be used in clean
        self.quality_assurance_fields = ('ref_knows_applicant',
                                         'ref_approves',
                                         'ref_understands_privacy')

        self.responder = responder
        self.fields['decision'].choices = REVIEW_RESPONSE_CHOICES

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['decision'] == '1':
            for field in self.quality_assurance_fields:
                if not self.cleaned_data[field]:
                    raise forms.ValidationError(
                        'The quality assurance fields must all pass '
                          'before you approve the application')

        if self.cleaned_data['decision'] == '0' and not self.cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject, you must explain why.')

    def save(self):
        application = super().save()
        if self.cleaned_data['decision'] == '0':
            application.reject(self.responder)
        elif self.cleaned_data['decision'] == '1':
            application.update_review_status(50)
        else:
            raise forms.ValidationError('Application status not valid.')

        return application


class AlterCommentsCredentialForm(forms.ModelForm):
    """
    Change the response comments on a processed application
    """
    class Meta:
        model = CredentialReview
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


class PublishedProjectContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ('name', 'affiliations', 'email')

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def save(self):
        contact = super().save(commit=False)
        contact.project = self.project
        contact.save()
        return contact


class CreateLegacyAuthorForm(forms.ModelForm):
    """
    Create an author for a legacy project.
    """
    author = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=autocomplete.ModelSelect2(url='user-autocomplete'),
        required=True,
        label="Author's username")

    class Meta:
        model = PublishedAffiliation
        fields = ('name',)
        labels = {'name': 'Affiliation', }

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean_author(self):
        author = self.cleaned_data['author']

        if self.project.authors.filter(user=author):
            raise forms.ValidationError('The person is already an author.')
        return author

    def save(self):
        if self.errors:
            return

        author = self.cleaned_data['author']
        affiliation = super().save(commit=False)
        display_order = self.project.authors.count() + 1
        is_submitting = False
        is_corresponding = False
        corresponding_email = None
        if display_order == 1:
            is_submitting = True
            is_corresponding = True
            corresponding_email = author.email

        affiliation.author = PublishedAuthor.objects.create(
            first_names=author.profile.first_names, project=self.project,
            last_name=author.profile.last_name, user=author,
            display_order=display_order, is_submitting=is_submitting,
            is_corresponding=is_corresponding,
            corresponding_email=corresponding_email)

        affiliation.save()
        return affiliation


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ('title', 'content')

    def __init__(self, page, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page

    def save(self):
        section = super().save(commit=False)
        section.page = self.page
        if not section.order:
            section.order = Section.objects.filter(page=self.page).count() + 1
        section.save()
        return section


class TrainingQuestionForm(forms.ModelForm):
    class Meta:
        model = TrainingQuestion
        fields = ('answer',)
        widgets = {'answer': forms.RadioSelect(choices=YES_NO_UNDETERMINED_REVIEW)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['answer'].label = self.instance.question.content


class TrainingQuestionFormSet(forms.BaseModelFormSet):
    def clean(self):
        if any(self.errors):
            return

        for form in self.forms:
            if not form.cleaned_data['answer']:
                raise forms.ValidationError(
                    'The quality assurance fields must all pass before you approve the application.'
                )


class TrainingReviewForm(forms.Form):
    reviewer_comments = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}), required=False)

    def clean(self):
        if self.errors:
            return

        if not self.cleaned_data['reviewer_comments']:
            raise forms.ValidationError('If you reject, you must explain why.')
