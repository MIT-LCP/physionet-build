from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation

from .models import AssociatedEmail, User, Profile


class AssociatedEmailChoiceForm(forms.Form):
    """
    For letting users choose one of their AssociatedEmails.
    Ie. primary email, contact email, remove email.
    """
    associated_email = forms.ModelChoiceField(queryset=None, to_field_name='email',
        label='email', widget=forms.Select(attrs={'class':'form-control'}))

    def __init__(self, user, include_primary=True, *args, **kwargs):
        # Email choices are those belonging to a user
        super(AssociatedEmailChoiceForm, self).__init__(*args, **kwargs)

        associated_emails = user.associated_emails.filter(verification_date__isnull=False)
        if include_primary:
            self.fields['associated_email'].queryset = associated_emails.order_by('-is_primary_email')
        else:
            self.fields['associated_email'].queryset = associated_emails.filter(is_primary_email=False)

    def set_label(self, label):
        self.fields['email'].label = label


class AssociatedEmailForm(forms.ModelForm):
    """
    For adding/editing new associated emails
    """
    class Meta:
        model = AssociatedEmail
        fields = ('email',)
        widgets = {
            'email':forms.EmailInput(attrs={'class':'form-control dropemail'}),
        }


class LoginForm(auth_forms.AuthenticationForm):
    """
    Form for logging in.
    """
    username = auth_forms.UsernameField(
        label='Email',
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': True, 'class':'form-control', 
            'placeholder':'Email Address'}),
    )
    password = forms.CharField(
        label= 'Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class':'form-control',
            'placeholder':'Password'}),
    )

    remember = forms.BooleanField(label='Remember Me', required=False)


class UserChangeForm(forms.ModelForm):
    """A form for updating user objects in the admin interface. Includes all
    fields on the user, but replaces the password field with the password hash
    display field. Use the admin interface to change passwords.
    """
    password = auth_forms.ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ('email', 'password', 'is_active', 'is_admin')

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]


class ProfileForm(forms.ModelForm):
    """
    For editing the profile
    """
    class Meta:
        model = Profile
        exclude = ('user', 'identity_verification_date')


class UserCreationForm(forms.ModelForm):
    """A form for creating new users. Includes all the required
    fields, plus a repeated password.
    """

    first_name = forms.CharField(max_length = 30, label='First Name',
                    widget=forms.TextInput(attrs={'class':'form-control'}))
    middle_names = forms.CharField(max_length = 100, label='Middle Names',
                    widget=forms.TextInput(attrs={'class':'form-control'}),
                    required=False)
    last_name = forms.CharField(max_length = 30, label='Last Name',
                    widget=forms.TextInput(attrs={'class':'form-control'}))
    password1 = forms.CharField(label='Password',
                    widget=forms.PasswordInput(attrs={'class':'form-control'}))
    password2 = forms.CharField(label='Password Confirmation',
                    widget=forms.PasswordInput(attrs={'class':'form-control'}))

    class Meta:
        model = User
        fields = ('email',)
        widgets = {
            'email':forms.EmailInput(attrs={'class':'form-control dropemail'}),
        }

    def clean_password2(self):
        # Check that the two password entries match
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The passwords don't match")
        self.instance.username = self.cleaned_data.get('username')
        password_validation.validate_password(self.cleaned_data.get('password2'), 
            self.instance)
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            # Save additional fields in Profile model
            profile = Profile.objects.create(user=user,
                first_name = self.cleaned_data['first_name'],
                middle_names = self.cleaned_data['middle_names'],
                last_name = self.cleaned_data['last_name'])
        return user
