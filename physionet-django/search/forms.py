from django import forms

from user.validators import validate_alphaplus


class TopicSearchForm(forms.Form):
    t = forms.CharField(max_length=50, label='Topic',
        validators=[validate_alphaplus])


class ProjectOrderForm(forms.Form):
    ORDER_CHOICES = (
        ('publish_datetime', 'Publish Date'),
        ('title', 'Title'),
        ('main_storage_size', 'Size'),
    )

    DIRECTION_CHOICES = (
        ('asc', 'Ascending'),
        ('desc', 'Descending')
    )

    order_param = forms.ChoiceField(choices=ORDER_CHOICES, label='Order By')
    direction = forms.ChoiceField(choices=DIRECTION_CHOICES, label='Direction')


    def clean_order_by(self):
        pass
