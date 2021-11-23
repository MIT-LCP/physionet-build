from django import forms
from django.db import transaction
from user.models import Profile, User
from user.validators import validate_name


class SSORegistrationForm(forms.ModelForm):
    first_names = forms.CharField(
        max_length=100,
        label='First Names',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        validators=[validate_name],
    )
    last_name = forms.CharField(
        max_length=50,
        label='Last Name',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        validators=[validate_name],
    )

    def __init__(self, *args, **kwargs):
        self.sso_id = kwargs.pop('sso_id', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = User
        fields = (
            'email',
            'username',
        )
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        "Record the original username in case it is needed"
        if User.objects.filter(username__iexact=self.cleaned_data['username']):
            raise forms.ValidationError("A user with that username already exists.")
        return self.cleaned_data['username'].lower()

    def save(self):
        """
        Process the registration form
        """
        if self.errors:
            return

        user = super().save(commit=False)
        user.email = user.email.lower()
        user.sso_id = self.sso_id

        with transaction.atomic():
            user.save()
            # Save additional fields in Profile model
            Profile.objects.create(
                user=user, first_names=self.cleaned_data['first_names'], last_name=self.cleaned_data['last_name']
            )
            return user
