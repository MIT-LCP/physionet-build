from django import forms
from .models import User
from django.contrib.auth.forms import ReadOnlyPasswordHashField, AuthenticationForm, UsernameField


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
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
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
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ('email', 'password', 'is_active', 'is_admin')

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]


class LoginForm(AuthenticationForm):
    """
    Form for logging in.
    """
    username = UsernameField(
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': True, 'class':'form-control', 'placeholder':'Email Address'}),
    )
    password = forms.CharField(
        label= 'Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Password'}),
    )

    remember = forms.BooleanField(label='Remember Me', required=False)

class ResetForm(AuthenticationForm):
    """
    Form to reset the password.
    """
    email = forms.EmailField(
        label='Email',
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': True, 'class':'form-control', 'placeholder':'Email Address'}),
    )

