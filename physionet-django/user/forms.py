from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation

from .models import User, Profile


class EmailForm(forms.Form):
    """
    Simple form with just an email. Used for adding emails and inheriting.
    """
    email = forms.EmailField(
        label='Email',
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': True, 'class':'form-control', 'placeholder':'Email Address'}),
    )


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
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The passwords don't match")
        self.instance.username = self.cleaned_data.get('username')
        password_validation.validate_password(self.cleaned_data.get('password2'), self.instance)
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.is_active = False
            # This should trigger profile creation
            user.save()
            # Save additional fields in Profile model
            user.profile.first_name = self.cleaned_data.get("first_name")
            user.profile.middle_names = self.cleaned_data.get("middle_names")
            user.profile.last_name = self.cleaned_data.get("last_name")
            user.profile.save()
        return user


class UserChangeForm(forms.ModelForm):
    """A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    password hash display field.
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


class LoginForm(auth_forms.AuthenticationForm):
    """
    Form for logging in.
    """
    username = auth_forms.UsernameField(
        label='Email',
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': True, 'class':'form-control', 'placeholder':'Email Address'}),
    )
    password = forms.CharField(
        label= 'Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Password'}),
    )

    remember = forms.BooleanField(label='Remember Me', required=False)


class ResetPasswordForm(auth_forms.PasswordResetForm, EmailForm):
    """
    Form to send the email to reset the password.
    """
    pass


class SetPasswordForm(auth_forms.SetPasswordForm):
    """
    Form to set or reset the password. Used in user creation and password reset.
    """
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={'autofocus': True, 'class':'form-control'}),
        strip=False,
    )
    new_password2 = forms.CharField(
        label="New password confirmation",
        strip=False,
        widget=forms.PasswordInput(attrs={'autofocus': True, 'class':'form-control'}),
        help_text=password_validation.password_validators_help_text_html(),
    )


class ProfileForm(forms.ModelForm):
    """
    For editing the profile
    """
    class Meta:
        model = Profile
        exclude = ('user', 'identity_verification_date')
        widgets = {
            'first_name':forms.TextInput(attrs={'class':'form-control'}),
            'middle_names':forms.TextInput(attrs={'class':'form-control'}),
            'last_name':forms.TextInput(attrs={'class':'form-control'}),
            'url':forms.TextInput(attrs={'class':'form-control'}),
            'phone':forms.TextInput(attrs={'class':'form-control'}),
        }


class EditPasswordForm(SetPasswordForm, auth_forms.PasswordChangeForm):
    """
    For editing password
    """
    old_password = forms.CharField(
        label="Old password",
        strip=False,
        widget=forms.PasswordInput(attrs={'autofocus': True, 'class':'form-control'}),
    )


class EmailChoiceForm(forms.Form):
    """
    For letting users choose one of their AssociatedEmails.
    Ie. primary email, contact email.
    """
    email_choice = forms.ModelChoiceField(queryset=None, to_field_name = 'email', 
        widget=forms.Select(attrs={'class':'form-control'}))

    def __init__(self, user, label, include_primary=True):
        """
        Can include or exclude the primary email
        """
        super(EmailChoiceForm, self).__init__()
        emails = user.associated_emails

        if include_primary:
            self.fields['email_choice'].queryset = emails.order_by('-is_primary_email')
            self.fields['email_choice'].initial = emails.get(is_primary_email=True)
        else:
            self.fields['email_choice'].queryset = emails.filter(is_primary_email=False)

        self.fields['email_choice'].label = label
