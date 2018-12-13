from django import forms

from user.validators import validate_alphaplus


class TopicSearchForm(forms.Form):
    description = forms.CharField(max_length=50, label='Topic',
        validators=[validate_alphaplus])
