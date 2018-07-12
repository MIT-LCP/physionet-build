from django import forms

from project.models import Submission
from user.models import User


class AssignEditorForm(forms.Form):
    """
    Assign an editor to a submission
    """
    submission = forms.ModelChoiceField(queryset=Submission.objects.filter(submission_status=2))
    editor = forms.ModelChoiceField(queryset=User.objects.filter(is_admin=True))
