from django import forms
from django.db.models import Max, F

from training.models import OnPlatformTraining
from user.models import TrainingType
from user.enums import RequiredField


class OnPlatformTrainingForm(forms.ModelForm):

    class Meta:
        model = OnPlatformTraining
        fields = ('training', )
        labels = {'training': 'Training Type'}

    def __init__(self, *args, **kwargs):
        training_id = kwargs.pop('training_type', None)
        super().__init__(*args, **kwargs)
        self.fields['training'].queryset = self.fields['training'].queryset.annotate(
            max_version=Max('op_trainings__version')).filter(
                op_trainings__version=F('max_version')).filter(
                    required_field=RequiredField.PLATFORM)

        self.training = TrainingType.objects.filter(id=training_id).first()

        self.fields['training'].initial = self.training

        if self.training:
            self.fields['training'].help_text = self.training.description
