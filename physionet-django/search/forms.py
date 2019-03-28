from django import forms

from user.validators import validate_alphaplus

class TopicSearchForm(forms.Form):
    topic = forms.CharField(max_length=50, validators=[validate_alphaplus])


class ProjectOrderForm(forms.Form):
    ORDER_CHOICES = (
        ('publish_datetime', 'Publish Date'),
        ('title', 'Title'),
        ('main_storage_size', 'Size'),
    )

    DIRECTION_CHOICES = (
        ('desc', 'Descending'),
        ('asc', 'Ascending'),
    )

    orderby = forms.ChoiceField(choices=ORDER_CHOICES, label='By')
    direction = forms.ChoiceField(choices=DIRECTION_CHOICES, label='Order')


    def clean_order_by(self):
        pass

class ProjectTypeForm(forms.Form):
    PROJECT_TYPES = (
        (0, 'Data'),
        (1, 'Software'),
        (2, 'Challenge'),
    )

    types = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=PROJECT_TYPES, label='')
