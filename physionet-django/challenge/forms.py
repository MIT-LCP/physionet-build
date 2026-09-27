from django import forms
from django.conf import settings

from challenge.models import (
    Challenge,
    ChallengeConfiguration,
    SubmissionSpec,
    Team,
)


class JSONPlaceholderTextarea(forms.Textarea):
    """Textarea that shows a placeholder when the JSON value is empty."""

    def format_value(self, value):
        if value in (None, '', '{}', '[]', 'null'):
            return ''
        return value


class ChallengeConfigurationForm(forms.ModelForm):
    """
    Form for editing ChallengeConfiguration during project submission.
    """
    validation_data_archive = forms.FileField(
        required=False,
        help_text='Upload validation data as a .tar.gz or .zip archive.',
    )
    test_data_archive = forms.FileField(
        required=False,
        help_text='Upload test data as a .tar.gz or .zip archive.',
    )
    evaluation_script_file = forms.FileField(
        required=False,
        help_text='Upload a Python scoring script (e.g. evaluate.py). '
                  'The script is called as: python evaluate.py '
                  '&lt;predictions_dir&gt; &lt;labels_dir&gt; &lt;scores_output&gt;. '
                  'It must write a JSON file to scores_output mapping metric '
                  'names to numeric values.',
    )

    class Meta:
        model = ChallengeConfiguration
        exclude = (
            'active_project',
            'validation_data_gcs_uri',
            'test_data_gcs_uri',
            'evaluation_script_gcs_uri',
        )
        widgets = {
            'registration_open_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'official_start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'input_format': JSONPlaceholderTextarea(attrs={
                'rows': 4,
                'placeholder': '{"type": "directory", "path": "/data/test", "description": "Directory of CSV files, one per patient record", "columns": ["timestamp", "MAP", "SBP", "DBP", "HR", "RR", "SpO2"]}',
            }),
            'output_format': JSONPlaceholderTextarea(attrs={
                'rows': 4,
                'placeholder': '{"type": "csv", "path": "/output/predictions.csv", "description": "One row per test record with binary prediction and continuous risk score", "columns": ["record_id", "prediction", "risk_score"]}',
            }),
            'primary_metric': JSONPlaceholderTextarea(attrs={
                'rows': 3,
                'placeholder': '{"name": "AUROC", "display_name": "AUROC", "sort": "desc"}',
            }),
            'additional_metrics': JSONPlaceholderTextarea(attrs={
                'rows': 4,
                'placeholder': '[{"name": "Sensitivity", "display_name": "Sensitivity", "sort": "desc"}, {"name": "PPV", "display_name": "PPV", "sort": "desc"}]',
            }),
        }

    def __init__(self, editable=True, **kwargs):
        super().__init__(**kwargs)
        if not editable:
            for field in self.fields.values():
                field.disabled = True

    def _validate_archive(self, field_name):
        archive = self.cleaned_data.get(field_name)
        if archive:
            valid_extensions = ('.tar.gz', '.tgz', '.zip')
            if not any(archive.name.endswith(ext) for ext in valid_extensions):
                raise forms.ValidationError(
                    'Upload must be a .tar.gz or .zip archive.'
                )
        return archive

    def clean_input_format(self):
        return self.cleaned_data.get('input_format') or {}

    def clean_output_format(self):
        return self.cleaned_data.get('output_format') or {}

    def clean_primary_metric(self):
        return self.cleaned_data.get('primary_metric') or {}

    def clean_additional_metrics(self):
        return self.cleaned_data.get('additional_metrics') or []

    def clean_validation_data_archive(self):
        return self._validate_archive('validation_data_archive')

    def clean_test_data_archive(self):
        return self._validate_archive('test_data_archive')

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_datetime')
        official_start = cleaned_data.get('official_start_datetime')
        end = cleaned_data.get('end_datetime')
        reg_open = cleaned_data.get('registration_open_datetime')

        if start and end and start >= end:
            raise forms.ValidationError(
                'End date must be after start date.'
            )
        if reg_open and start and reg_open > start:
            raise forms.ValidationError(
                'Registration must open before the challenge starts.'
            )
        if start and official_start and official_start <= start:
            raise forms.ValidationError(
                'Official phase must start after the unofficial phase.'
            )
        if official_start and end and official_start >= end:
            raise forms.ValidationError(
                'Official phase must start before the end date.'
            )
        return cleaned_data


class ChallengeConfigForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = [
            'organizer_name',
            'registration_open_datetime', 'start_datetime',
            'official_start_datetime', 'end_datetime',
            'rules', 'evaluation_description', 'prizes',
            'max_submissions_per_day', 'max_total_submissions',
            'teams_enabled', 'is_active',
        ]
        widgets = {
            'registration_open_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'official_start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_datetime')
        official_start = cleaned_data.get('official_start_datetime')
        end = cleaned_data.get('end_datetime')
        reg_open = cleaned_data.get('registration_open_datetime')

        if start and end and start >= end:
            raise forms.ValidationError(
                'End date must be after start date.'
            )
        if reg_open and start and reg_open > start:
            raise forms.ValidationError(
                'Registration must open before the challenge starts.'
            )
        if start and official_start and official_start <= start:
            raise forms.ValidationError(
                'Official phase must start after the unofficial phase.'
            )
        if official_start and end and official_start >= end:
            raise forms.ValidationError(
                'Official phase must start before the end date.'
            )
        return cleaned_data


class ChallengeManageForm(forms.ModelForm):
    """
    Form for editing challenge settings from the manage page.
    Covers dates, limits, phase, and active status.
    """
    class Meta:
        model = Challenge
        fields = [
            'phase',
            'registration_open_datetime', 'start_datetime',
            'official_start_datetime', 'end_datetime',
            'max_submissions_per_day', 'max_total_submissions',
            'max_submissions_to_advance', 'teams_enabled', 'is_active',
        ]
        widgets = {
            'registration_open_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'official_start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_datetime')
        official_start = cleaned_data.get('official_start_datetime')
        end = cleaned_data.get('end_datetime')
        reg_open = cleaned_data.get('registration_open_datetime')

        if start and end and start >= end:
            raise forms.ValidationError(
                'End date must be after start date.'
            )
        if reg_open and start and reg_open > start:
            raise forms.ValidationError(
                'Registration must open before the challenge starts.'
            )
        if start and official_start and official_start <= start:
            raise forms.ValidationError(
                'Official phase must start after the unofficial phase.'
            )
        if official_start and end and official_start >= end:
            raise forms.ValidationError(
                'Official phase must start before the end date.'
            )
        return cleaned_data


class SubmissionSpecForm(forms.ModelForm):
    class Meta:
        model = SubmissionSpec
        fields = [
            'base_image', 'entrypoint_command',
            'max_runtime_seconds', 'max_memory_mb',
            'gpu_enabled', 'gpu_type', 'cpu_count',
            'input_format', 'output_format',
            'primary_metric', 'additional_metrics',
        ]

    def clean_input_format(self):
        return self.cleaned_data.get('input_format') or {}

    def clean_output_format(self):
        return self.cleaned_data.get('output_format') or {}

    def clean_primary_metric(self):
        return self.cleaned_data.get('primary_metric') or {}

    def clean_additional_metrics(self):
        return self.cleaned_data.get('additional_metrics') or []


class CodeSubmissionForm(forms.Form):
    code_archive = forms.FileField(
        help_text='Upload a .tar.gz or .zip archive (max 100 MB).',
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional notes about this submission.',
    )

    def clean_code_archive(self):
        archive = self.cleaned_data['code_archive']
        max_size = getattr(
            settings, 'CHALLENGE_MAX_ARCHIVE_SIZE_MB', 100
        ) * 1024 * 1024
        if archive.size > max_size:
            raise forms.ValidationError(
                f'Archive exceeds maximum size of '
                f'{max_size // (1024 * 1024)} MB.'
            )
        valid_extensions = ('.tar.gz', '.tgz', '.zip')
        if not any(archive.name.endswith(ext) for ext in valid_extensions):
            raise forms.ValidationError(
                'Upload must be a .tar.gz or .zip archive.'
            )
        return archive


class HiddenTestDataForm(forms.Form):
    test_data_archive = forms.FileField(
        help_text='Upload hidden test data as .tar.gz or .zip archive.',
    )

    def clean_test_data_archive(self):
        archive = self.cleaned_data['test_data_archive']
        valid_extensions = ('.tar.gz', '.tgz', '.zip')
        if not any(archive.name.endswith(ext) for ext in valid_extensions):
            raise forms.ValidationError(
                'Upload must be a .tar.gz or .zip archive.'
            )
        return archive


class EvaluationScriptForm(forms.Form):
    evaluation_script = forms.FileField(
        help_text='Upload the evaluation/scoring script.',
    )


class TeamCreateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name']


class TeamInviteForm(forms.Form):
    email = forms.EmailField(
        help_text='Email address of the person to invite.',
    )


class TeamInvitationResponseForm(forms.Form):
    CHOICES = [
        (True, 'Accept'),
        (False, 'Decline'),
    ]
    accept = forms.TypedChoiceField(
        choices=CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect,
    )
