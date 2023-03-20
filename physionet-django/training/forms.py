from django import forms
from django.db.models import Max, F

from training.models import OnPlatformTraining
from user.models import TrainingType
from user.enums import RequiredField


class OnPlatformTrainingForm(forms.ModelForm):

    class Meta:
        model = OnPlatformTraining
        fields = ('training_type', )
        labels = {'training_type': 'Training Type'}

    def __init__(self, *args, **kwargs):
        training_id = kwargs.pop('training_type', None)
        super().__init__(*args, **kwargs)
        self.fields['training_type'].queryset = self.fields['training_type'].queryset.annotate(
            max_version=Max('op_trainings__version')).filter(
                op_trainings__version=F('max_version')).filter(
                    required_field=RequiredField.PLATFORM)

        self.training_type = TrainingType.objects.filter(id=training_id).first()

        self.fields['training_type'].initial = self.training_type

        if self.training_type:
            self.fields['training_type'].help_text = self.training_type.description
