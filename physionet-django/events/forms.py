from django import forms

from events.widgets import DatePickerInput
from events.models import Event, EventApplication, EventAgreement, EventDataset
from project.models import PublishedProject


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
                   }

    def __init__(self, user, *args, **kwargs):
        self.host = user
        super(AddEventForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(AddEventForm, self).clean()
        if Event.objects.filter(title=cleaned_data['title'], host=self.host).exists():
            # in case of update, we don't want to raise an error if the title is the same
            if self.initial.get('title'):  # in case of update we have an initial value
                # if the instance title is different from the new title, then we have a duplicate with another event
                if self.instance.title != cleaned_data['title']:
                    raise forms.ValidationError({"title": ["Event with this title already exists"]})
            else:
                raise forms.ValidationError({"title": ["Event with this title already exists"]})

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


class EventApplicationResponseForm(forms.ModelForm):
    """
    For responding to a request to join an Event.
    """

    status = forms.ChoiceField(choices=EventApplication.EventApplicationStatus.choices_approval(),
                               widget=forms.Select)

    class Meta:
        model = EventApplication
        fields = ('status', 'comment_to_applicant')


class EventDatasetForm(forms.ModelForm):
    """
    A form for adding datasets to an event.
    """
    dataset = forms.ModelChoiceField(queryset=PublishedProject.objects.all(),
                                     widget=forms.Select(attrs={'class': 'form-control'}))

    class Meta:
        model = EventDataset
        fields = ('dataset', 'access_type')


class EventAgreementForm(forms.ModelForm):
    class Meta:
        model = EventAgreement
        fields = (
            'name',
            'version',
            'slug',
            'is_active',
            'html_content',
            'access_template',
        )
        labels = {'html_content': 'Content'}
        help_texts = {
            'name': '* The displayed name of the agreement.',
            'version': '* The version number of the agreement.',
            'slug': '* A simple string for use in the URL displaying the agreement. '
                    'Should include the version number.',
            'is_active': '* Only active agreements are usable in future events.',
            'html_content': '* The agreement text displayed to the participant.',
            'access_template': '* Instructions on accessing the dataset.'
        }

    def clean(self):
        cleaned_data = super(EventAgreementForm, self).clean()
        if EventAgreement.objects.filter(name=cleaned_data['name'], version=cleaned_data['version']).exists():
            if (self.initial.get('name') == cleaned_data['name']
                    and self.initial.get('version') == cleaned_data['version']):
                return cleaned_data
            raise forms.ValidationError(
                {"name": ["An agreement with this name and version already exists."],
                 "version": ["An agreement with this name and version already exists."]
                 })
        return cleaned_data
