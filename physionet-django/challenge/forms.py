from django import forms
from django.conf import settings

from challenge.models import (
    Challenge,
    ChallengeConfiguration,
    SubmissionSpec,
    Team,
)


class ChallengeConfigurationForm(forms.ModelForm):
    """
    Form for editing ChallengeConfiguration during project submission.
    """
    class Meta:
        model = ChallengeConfiguration
        exclude = ('active_project',)
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

    def __init__(self, editable=True, **kwargs):
        super().__init__(**kwargs)
        if not editable:
            for field in self.fields.values():
                field.disabled = True

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


class SubmissionSpecForm(forms.ModelForm):
    class Meta:
        model = SubmissionSpec
        fields = [
            'base_image', 'entrypoint_command',
            'max_runtime_seconds', 'max_memory_mb',
            'gpu_enabled', 'gpu_type', 'cpu_count',
            'input_format', 'output_format',
            'primary_metric_name', 'primary_metric_sort',
            'additional_metrics',
        ]


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
