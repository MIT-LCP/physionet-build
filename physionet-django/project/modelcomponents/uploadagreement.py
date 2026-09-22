from django.db import models


# Labels for the data type checkboxes, used by both the model and the form.
NO_HUMAN_SUBJECTS_LABEL = (
    'This project does not contain any data derived from human subjects.'
)
DERIVED_DATA_LABEL = (
    'This project contains data derived from other de-identified datasets.'
)
DERIVED_DATA_FORM_LABEL = (
    'This project contains data derived from other de-identified datasets '
    'published on {site_name} or elsewhere.'
)
HUMAN_SUBJECTS_DEIDENTIFIED_LABEL = (
    'This project contains data obtained from human subjects, and all '
    'personally identifiable information has been removed.'
)


class UploadAgreement(models.Model):
    """
    Model to track upload agreements for projects.
    Each author can have one upload agreement.
    """
    author = models.OneToOneField(
        'project.Author',
        on_delete=models.CASCADE,
        related_name='upload_agreement'
    )

    # Agreement acceptance
    accepted = models.BooleanField(
        default=False,
        help_text='Whether the upload agreement has been accepted'
    )

    accepted_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the upload agreement was accepted'
    )

    # Data type options (at least one must be selected)
    no_human_subjects = models.BooleanField(
        default=False,
        help_text=NO_HUMAN_SUBJECTS_LABEL,
    )

    derived_data = models.BooleanField(
        default=False,
        help_text=DERIVED_DATA_LABEL,
    )

    human_subjects_deidentified = models.BooleanField(
        default=False,
        help_text=HUMAN_SUBJECTS_DEIDENTIFIED_LABEL,
    )

    # Metadata
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_uploadagreement'
        verbose_name = 'Upload Agreement'
        verbose_name_plural = 'Upload Agreements'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(no_human_subjects=True)
                    | models.Q(derived_data=True)
                    | models.Q(human_subjects_deidentified=True)
                ),
                name='at_least_one_data_type_selected',
                violation_error_message='Please select at least one option that applies to your project.',
            )
        ]

    def selected_data_types(self):
        """Return the labels of the selected data type checkboxes."""
        labels = []
        if self.no_human_subjects:
            labels.append(NO_HUMAN_SUBJECTS_LABEL)
        if self.derived_data:
            labels.append(DERIVED_DATA_LABEL)
        if self.human_subjects_deidentified:
            labels.append(HUMAN_SUBJECTS_DEIDENTIFIED_LABEL)
        return labels

    def __str__(self):
        return (
            f"Upload Agreement for {self.author} - "
            f"{'Accepted' if self.accepted else 'Pending'}"
        )
