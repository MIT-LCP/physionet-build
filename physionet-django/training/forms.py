from django import forms
from django.db.models import Max, F, OuterRef

from training.models import Course
from user.models import TrainingType
from user.enums import RequiredField


class CourseForm(forms.ModelForm):

    class Meta:
        model = Course
        fields = ('training_type', )
        labels = {'training_type': 'Training Type'}

    def __init__(self, *args, **kwargs):
        training_id = kwargs.pop('training_type', None)
        super().__init__(*args, **kwargs)

        self.fields['training_type'].queryset = self.fields['training_type'].queryset.annotate(
            max_version=Max('courses__version')
        ).filter(
            courses__version=F('max_version'),
            required_field=RequiredField.PLATFORM,
            courses__is_active=True
        )

        self.training_type = TrainingType.objects.filter(id=training_id).first()

        self.fields['training_type'].initial = self.training_type

        if self.training_type:
            self.fields['training_type'].help_text = self.training_type.description
