from django import forms

from events.widgets import DatePickerInput
from events.models import Event


class AddEventForm(forms.ModelForm):
    """
    A form for adding events.
    """
    class Meta:
        model = Event
        fields = ('title', 'description', 'start_date', 'end_date',
                  'category', 'allowed_domains')
        labels = {'title': 'Event Name', 'description': 'Description',
                  'start_date': 'Start Date', 'end_date': 'End Date',
                  'category': 'Category', 'allowed_domains': 'Allowed domains'}
        widgets = {'start_date': DatePickerInput(),
                   'end_date': DatePickerInput(),
                   'description': forms.Textarea(attrs={'rows': 4, 'cols': 40})}

    def __init__(self, user, *args, **kwargs):
        self.host = user
        super(AddEventForm, self).__init__(*args, **kwargs)

    def save(self):
        # Handle updating the event
        if self.initial:
            self.instance.save()
        else:
            Event.objects.create(title=self.cleaned_data['title'],
                                 category=self.cleaned_data['category'],
                                 host=self.host,
                                 description=self.cleaned_data['description'],
                                 start_date=self.cleaned_data['start_date'],
                                 end_date=self.cleaned_data['end_date'],
                                 allowed_domains=self.cleaned_data['allowed_domains']
                                 )
