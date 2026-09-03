from django.db import models


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
        help_text='This project does not contain any data derived from human subjects'
    )

    derived_data = models.BooleanField(
        default=False,
        help_text='This project contains data derived from other de-identified datasets'
    )

    human_subjects_deidentified = models.BooleanField(
        default=False,
        help_text=(
            'This project contains data obtained from human subjects, and all '
            'personally identifiable information has been removed'
        )
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

    def __str__(self):
        return (
            f"Upload Agreement for {self.author} - "
            f"{'Accepted' if self.accepted else 'Pending'}"
        )

