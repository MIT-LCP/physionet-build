from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django import forms
from .models import User
from re import search, match

class UserCreationForm(forms.ModelForm):
    """A form for creating new users. Includes all the required
    fields, plus a repeated password.

    This is a ModelForm which takes attributes from the User model.
    """

    # Since password is not a field in the User model, these form fields
    # must be specified here
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('email',)

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
            user.save()
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


class BaseUserForm():
    class Meta:
        model   = User
        fields  = ['email', 'url']
        widgets = {
            'email' : forms.EmailInput(attrs={'class': 'form-control', 'name': 'email', 'readonly':'True'}),
            'url'   : forms.TextInput(attrs={'class': 'form-control', 'name': 'Url'}),
        }
        
    def clean_password(self):
        Password = self.cleaned_data.get('Password' , False)
        if Password:
            if len(Password) < 8:
                raise ValidationError({'Password': ["The password is too short."]})
            if len(Password) > 15:
                raise ValidationError({'Password': ["The password is too long, it cannot have more than 15 characters.",]})
            if not bool(search(r'\d', Password)):
                raise ValidationError({'Password': ["The password must contain at least 1 digit.",]})
            if not bool(search(r'[a-zA-Z]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 letter.",]})
            if not bool(search(r'[~!@#$.%&?^*]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 special character. Acccepted are: ~ ! @ # $ % & ? ^ *",]})
            if Password.isupper() or Password.islower():
                raise ValidationError({'Password': ["The password must contain upper and lower case letters.",]})
            return Password
        else:
            return None

    def clean_logged_email(self):
        Email = self.cleaned_data.get('email' , False)
        if Email:
            Exists = True
            try:
                Person = User.objects.get(email=Email)
            except ObjectDoesNotExist:
                Exists = False
            if not Exists:
                raise ValidationError({'email': ['The email is already registered.',]})
            if not match(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', Email):
                raise ValidationError({'email': ['Invalid email.',]})
            return Email

class LoginForm(BaseUserForm, forms.Form):
    email = forms.CharField(label="Email",max_length=50,required=True,widget=forms.EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    Password = forms.CharField(label="Password",max_length=15,required=True,widget=forms.PasswordInput(attrs={'class':'form-control','name':'Password'}))
    
    def clean(self):
        Pass  = BaseUserForm.clean_password(self)
        email = BaseUserForm.clean_logged_email(self)
        super(LoginForm, self).clean()








