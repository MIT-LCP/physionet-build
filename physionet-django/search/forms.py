from django import forms

class TopicSearchForm(forms.Form):
    topic = forms.CharField(max_length=50, required=False, label='')


class ProjectOrderForm(forms.Form):
    ORDER_CHOICES = (
        ('relevance-desc', 'Relevance'),
        ('publish_datetime-desc', 'Latest'),
        ('publish_datetime-asc', 'Oldest'),
        ('title-asc', 'Title (Asc.)'),
        ('title-desc', 'Title (Desc.)'),
        ('main_storage_size-asc', 'Size (Asc.)'),
        ('main_storage_size-desc', 'Size (Desc.)'),
    )

    orderby = forms.ChoiceField(choices=ORDER_CHOICES, label='')

    def clean_order_by(self):
        pass


class ProjectTypeForm(forms.Form):
    PROJECT_TYPES = (
        (0, 'Data'),
        (1, 'Software'),
        (2, 'Challenge'),
        (3, 'Model'),
    )

    types = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                      choices=PROJECT_TYPES, label='')
